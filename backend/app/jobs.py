from __future__ import annotations

import asyncio
import logging
import threading
from functools import lru_cache
from uuid import uuid4

import httpx

from .artifacts import get_artifact_store
from .config import get_settings
from .graph import run_claim
from .observability import (
    bind_claim_context,
    clear_context,
    ensure_trace_id,
    get_trace_id,
    log_event,
    log_usage_summary,
)
from .signal_artifacts import persist_signal_artifacts
from .storage import (
    create_or_update_claim,
    get_claim,
    get_original_artifact_record,
    mark_claim_failed,
    mark_claim_processing,
)

logger = logging.getLogger(__name__)


@lru_cache
def build_celery_app():
    from celery import Celery

    settings = get_settings()
    celery = Celery(
        "truthpixel",
        broker=settings.redis_url,
        backend=settings.celery_result_backend or settings.redis_url,
    )
    celery.conf.update(
        task_always_eager=settings.celery_task_always_eager,
        task_ignore_result=False,
        result_extended=True,
    )
    return celery


def reset_job_state() -> None:
    build_celery_app.cache_clear()


def _dispatch_webhook(claim_id: str) -> None:
    claim = get_claim(claim_id)
    if claim is None or not claim.webhook_url:
        return
    try:
        response = httpx.post(
            claim.webhook_url,
            json=claim.model_dump(mode="json"),
            timeout=get_settings().webhook_timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log_event(
            logger,
            "claim_webhook_failed",
            webhook_url=claim.webhook_url,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        logger.warning("Webhook dispatch failed for claim %s: %s", claim_id, exc)
    else:
        log_event(logger, "claim_webhook_dispatched", webhook_url=claim.webhook_url)
        logger.info("Webhook dispatched for claim %s", claim_id)


def process_claim_job(claim_id: str, trace_id: str | None = None) -> None:
    clear_context()
    ensure_trace_id(trace_id)
    bind_claim_context(claim_id=claim_id)
    log_event(logger, "claim_job_started")
    mark_claim_processing(claim_id)
    claim = get_claim(claim_id)
    original = get_original_artifact_record(claim_id)
    if claim is None or original is None:
        mark_claim_failed(claim_id, "missing claim record or original artifact")
        log_event(logger, "claim_job_missing_inputs")
        log_usage_summary(logger, reason="missing_inputs")
        clear_context()
        return

    try:
        bind_claim_context(tenant_id=claim.tenant_id)
        image = get_artifact_store().get_bytes(original.storage_key)
        report = _run_claim_sync(image, claim.context, claim_id)
        persist_signal_artifacts(claim_id, report.signals, tenant_id=claim.tenant_id)
        create_or_update_claim(report)
        log_event(
            logger,
            "claim_job_completed",
            risk_score=report.fusion.risk_score,
            needs_review=report.fusion.needs_review,
            signal_count=len(report.signals),
        )
        log_usage_summary(logger, outcome="completed")
        _dispatch_webhook(claim_id)
    except Exception as exc:  # noqa: BLE001
        mark_claim_failed(claim_id, f"{type(exc).__name__}: {exc}")
        log_event(
            logger,
            "claim_job_failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        log_usage_summary(logger, outcome="failed")
    finally:
        clear_context()


def _run_claim_sync(image: bytes, context, claim_id: str):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_claim(image, context, claim_id=claim_id))

    result: dict[str, object] = {}
    failure: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["report"] = asyncio.run(run_claim(image, context, claim_id=claim_id))
        except BaseException as exc:  # noqa: BLE001
            failure["exc"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "exc" in failure:
        raise failure["exc"]
    return result["report"]


def register_tasks(celery_app):
    @celery_app.task(name="truthpixel.process_claim")
    def process_claim_task(claim_id: str, trace_id: str | None = None) -> None:
        process_claim_job(claim_id, trace_id=trace_id)

    return process_claim_task


def enqueue_claim_processing(claim_id: str) -> str:
    settings = get_settings()
    request_trace_id = get_trace_id()
    if settings.celery_task_always_eager:
        task_id = f"eager-{uuid4().hex}"
        if request_trace_id is None:
            request_trace_id = ensure_trace_id()
        bind_claim_context(claim_id=claim_id)
        log_event(logger, "claim_job_eager_dispatch", task_id=task_id)
        process_claim_job(claim_id, trace_id=request_trace_id)
        if request_trace_id is not None:
            ensure_trace_id(request_trace_id)
            bind_claim_context(claim_id=claim_id)
        return task_id

    celery_app = build_celery_app()
    register_tasks(celery_app)
    result = celery_app.send_task("truthpixel.process_claim", args=[claim_id, request_trace_id])
    if request_trace_id is None:
        ensure_trace_id()
    bind_claim_context(claim_id=claim_id)
    log_event(logger, "claim_job_queued", task_id=str(result.id))
    return str(result.id)
