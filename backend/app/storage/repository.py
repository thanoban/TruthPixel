from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..schemas import (
    ArtifactKind,
    AggregatedUsageProviderBreakdown,
    AuditEvent,
    ClaimArtifact,
    ClaimDecision,
    ClaimDecisionRequest,
    ClaimListItem,
    ClaimReport,
    ClaimUsageSummary,
    ClaimQueueStatus,
    ClaimContext,
    ClaimStatus,
    FusionResult,
    IssuedApiKeyResponse,
    StoredClaim,
    TenantUsageSummary,
    TenantResponse,
    UsageProviderBreakdown,
)
from .models import (
    ApiKeyRecord,
    ArtifactRecord,
    AuditEventRecord,
    ClaimRecord,
    ClaimUsageSummaryRecord,
    RateLimitEventRecord,
    TenantRecord,
    utc_now,
)


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, **_engine_kwargs(settings.database_url))


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def reset_storage_state() -> None:
    get_session_factory.cache_clear()
    engine = None
    if get_engine.cache_info().currsize:
        engine = get_engine()
    get_engine.cache_clear()
    if engine is not None:
        engine.dispose()


def _run_alembic_upgrade() -> None:
    """Run migrations up to head via Alembic (backend/alembic/) instead of the old
    Base.metadata.create_all()-only approach, which created missing tables but never
    altered existing ones — see backend/alembic/versions/0001_baseline_schema.py for the
    incident that motivated switching to a real migration framework (docs/CORRECTIONS.md
    2026-07-09/10). Alembic's env.py reads DATABASE_URL from get_settings() itself, so this
    always targets whatever DB the app/tests are currently configured for.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent.parent
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(cfg, "head")


def init_db() -> None:
    _run_alembic_upgrade()


@contextmanager
def session_scope():
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _claim_to_schema(record: ClaimRecord) -> StoredClaim:
    decision = ClaimDecision.model_validate(record.decision_json) if record.decision_json else None
    return StoredClaim(
        claim_id=record.claim_id,
        tenant_id=record.tenant_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        status=record.status,
        task_id=record.task_id,
        error_message=record.error_message,
        webhook_url=record.webhook_url,
        started_at=record.started_at,
        completed_at=record.completed_at,
        context=ClaimContext.model_validate(record.context_json),
        signals=record.signals_json,
        agent_findings=record.agent_findings_json,
        fusion=record.fusion_json,
        report_text=record.report_text,
        disclaimer=record.disclaimer,
        decision=decision,
        artifacts=[_artifact_to_schema(item) for item in sorted(record.artifacts, key=lambda a: a.id)],
    )


def _artifact_to_schema(record: ArtifactRecord) -> ClaimArtifact:
    return ClaimArtifact(
        id=record.id,
        claim_id=record.claim_id,
        kind=record.kind,
        filename=record.filename,
        media_type=record.media_type,
        byte_size=record.byte_size,
        sha256=record.sha256,
        storage_backend=record.storage_backend,
        download_path=f"/v1/claims/{record.claim_id}/artifacts/{record.id}",
        created_at=record.created_at,
    )


def _placeholder_fusion() -> dict:
    return FusionResult(
        risk_score=0.5,
        needs_review=True,
        contributions={},
        fusion_version="queued-0.1",
    ).model_dump(mode="json")


def _queue_status(record: ClaimRecord) -> ClaimQueueStatus:
    return ClaimQueueStatus(
        claim_id=record.claim_id,
        tenant_id=record.tenant_id,
        status=record.status,
        task_id=record.task_id,
        error_message=record.error_message,
        webhook_url=record.webhook_url,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        poll_path=f"/v1/claims/{record.claim_id}/status",
    )


def _append_audit_event(session: Session, claim_id: str, event_type: str, payload: dict) -> None:
    session.add(
        AuditEventRecord(
            claim_id=claim_id,
            event_type=event_type,
            payload_json=payload,
        )
    )


def _tenant_to_schema(record: TenantRecord) -> TenantResponse:
    return TenantResponse(
        tenant_id=record.tenant_id,
        name=record.name,
        is_active=record.is_active,
        rate_limit_requests=record.rate_limit_requests,
        rate_limit_window_seconds=record.rate_limit_window_seconds,
        created_at=record.created_at,
    )


def _empty_usage_provider_dict() -> dict[str, UsageProviderBreakdown]:
    return {}


def _claim_usage_to_schema(record: ClaimUsageSummaryRecord) -> ClaimUsageSummary:
    providers_payload = record.providers_json if isinstance(record.providers_json, dict) else {}
    return ClaimUsageSummary(
        claim_id=record.claim_id,
        tenant_id=record.tenant_id,
        outcome=record.outcome,
        total_external_requests=record.total_external_requests,
        failed_external_requests=record.failed_external_requests,
        total_input_tokens=record.total_input_tokens,
        total_output_tokens=record.total_output_tokens,
        estimated_cost_usd=round(float(record.estimated_cost_usd), 8),
        providers={
            name: UsageProviderBreakdown.model_validate(payload)
            for name, payload in sorted(providers_payload.items())
        },
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _empty_claim_usage_summary(
    *, claim_id: str, tenant_id: str | None, created_at: datetime, updated_at: datetime, outcome: str = ""
) -> ClaimUsageSummary:
    return ClaimUsageSummary(
        claim_id=claim_id,
        tenant_id=tenant_id,
        outcome=outcome,
        total_external_requests=0,
        failed_external_requests=0,
        total_input_tokens=0,
        total_output_tokens=0,
        estimated_cost_usd=0.0,
        providers=_empty_usage_provider_dict(),
        created_at=created_at,
        updated_at=updated_at,
    )


def create_pending_claim(
    claim_id: str,
    context: ClaimContext,
    webhook_url: str = "",
    tenant_id: str | None = None,
) -> StoredClaim:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            record = ClaimRecord(claim_id=claim_id)
            session.add(record)
        if tenant_id is not None or record.tenant_id is None:
            record.tenant_id = tenant_id
        record.context_json = context.model_dump(mode="json")
        record.signals_json = []
        record.agent_findings_json = []
        record.fusion_json = _placeholder_fusion()
        record.report_text = "Queued for asynchronous analysis."
        record.disclaimer = (
            "Confidence-scored assessment, not a verdict. A human reviewer makes the final call."
        )
        record.status = ClaimStatus.PENDING.value
        record.error_message = None
        record.webhook_url = webhook_url or None
        record.started_at = None
        record.completed_at = None
        session.flush()
        _append_audit_event(
            session,
            claim_id,
            "claim_queued",
            {"webhook_url": webhook_url or None},
        )
        session.flush()
        session.refresh(record)
        return _claim_to_schema(record)


def create_processing_claim(
    claim_id: str,
    context: ClaimContext,
    tenant_id: str | None = None,
) -> StoredClaim:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            record = ClaimRecord(claim_id=claim_id)
            session.add(record)
        if tenant_id is not None or record.tenant_id is None:
            record.tenant_id = tenant_id
        record.context_json = context.model_dump(mode="json")
        record.signals_json = []
        record.agent_findings_json = []
        record.fusion_json = _placeholder_fusion()
        record.report_text = "Processing claim."
        record.disclaimer = (
            "Confidence-scored assessment, not a verdict. A human reviewer makes the final call."
        )
        record.status = ClaimStatus.PROCESSING.value
        record.task_id = None
        record.error_message = None
        if record.started_at is None:
            record.started_at = utc_now()
        record.completed_at = None
        session.flush()
        session.refresh(record)
        return _claim_to_schema(record)


def set_claim_task_info(claim_id: str, task_id: str | None) -> ClaimQueueStatus | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            return None
        record.task_id = task_id
        session.flush()
        session.refresh(record)
        return _queue_status(record)


def mark_claim_processing(claim_id: str) -> ClaimQueueStatus | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            return None
        record.status = ClaimStatus.PROCESSING.value
        record.error_message = None
        if record.started_at is None:
            record.started_at = utc_now()
        session.flush()
        _append_audit_event(session, claim_id, "claim_processing_started", {})
        session.flush()
        session.refresh(record)
        return _queue_status(record)


def create_or_update_claim(report: ClaimReport, tenant_id: str | None = None) -> StoredClaim:
    with session_scope() as session:
        record = session.get(ClaimRecord, report.claim_id)
        if record is None:
            record = ClaimRecord(claim_id=report.claim_id)
            session.add(record)
        if tenant_id is not None or record.tenant_id is None:
            record.tenant_id = tenant_id

        record.context_json = report.context.model_dump(mode="json")
        record.signals_json = [signal.model_dump(mode="json") for signal in report.signals]
        record.agent_findings_json = [
            finding.model_dump(mode="json") for finding in report.agent_findings
        ]
        record.fusion_json = report.fusion.model_dump(mode="json")
        record.report_text = report.report_text
        record.disclaimer = report.disclaimer
        record.status = ClaimStatus.COMPLETED.value
        record.error_message = None
        if record.started_at is None:
            record.started_at = utc_now()
        record.completed_at = utc_now()
        session.flush()

        _append_audit_event(
            session,
            report.claim_id,
            "claim_persisted",
            {
                "risk_score": report.fusion.risk_score,
                "needs_review": report.fusion.needs_review,
                "signal_count": len(report.signals),
            },
        )
        session.flush()
        session.refresh(record)
        return _claim_to_schema(record)


def upsert_claim_usage_summary(
    *,
    claim_id: str,
    tenant_id: str | None,
    outcome: str,
    summary: dict[str, Any],
) -> ClaimUsageSummary | None:
    with session_scope() as session:
        claim = session.get(ClaimRecord, claim_id)
        if claim is None:
            return None

        effective_tenant_id = tenant_id if tenant_id is not None else claim.tenant_id
        record = session.get(ClaimUsageSummaryRecord, claim_id)
        if record is None:
            record = ClaimUsageSummaryRecord(claim_id=claim_id)
            session.add(record)

        record.tenant_id = effective_tenant_id
        record.outcome = (outcome or "")[:40]
        record.total_external_requests = max(0, int(summary.get("total_external_requests", 0) or 0))
        record.failed_external_requests = max(
            0, int(summary.get("failed_external_requests", 0) or 0)
        )
        record.total_input_tokens = max(0, int(summary.get("total_input_tokens", 0) or 0))
        record.total_output_tokens = max(0, int(summary.get("total_output_tokens", 0) or 0))
        record.estimated_cost_usd = round(
            max(0.0, float(summary.get("estimated_cost_usd", 0.0) or 0.0)),
            8,
        )
        providers_payload = summary.get("providers", {})
        record.providers_json = providers_payload if isinstance(providers_payload, dict) else {}
        session.flush()
        session.refresh(record)
        return _claim_usage_to_schema(record)


def get_claim(claim_id: str, tenant_id: str | None = None) -> StoredClaim | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            return None
        if tenant_id is not None and record.tenant_id != tenant_id:
            return None
        return _claim_to_schema(record) if record else None


def get_claim_usage_summary(claim_id: str, tenant_id: str | None = None) -> ClaimUsageSummary | None:
    with session_scope() as session:
        claim = session.get(ClaimRecord, claim_id)
        if claim is None:
            return None
        if tenant_id is not None and claim.tenant_id != tenant_id:
            return None

        record = session.get(ClaimUsageSummaryRecord, claim_id)
        if record is None:
            return _empty_claim_usage_summary(
                claim_id=claim.claim_id,
                tenant_id=claim.tenant_id,
                created_at=claim.created_at,
                updated_at=claim.updated_at,
                outcome=claim.status,
            )
        return _claim_usage_to_schema(record)


def _aggregate_usage_providers(
    summaries: list[ClaimUsageSummary],
) -> dict[str, AggregatedUsageProviderBreakdown]:
    aggregate: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        for provider_name, provider in summary.providers.items():
            bucket = aggregate.setdefault(
                provider_name,
                {
                    "requests": 0,
                    "failed_requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0,
                    "operations": {},
                    "models": set(),
                    "claim_ids": set(),
                },
            )
            bucket["requests"] += provider.requests
            bucket["failed_requests"] += provider.failed_requests
            bucket["input_tokens"] += provider.input_tokens
            bucket["output_tokens"] += provider.output_tokens
            bucket["estimated_cost_usd"] = round(
                float(bucket["estimated_cost_usd"]) + float(provider.estimated_cost_usd),
                8,
            )
            for operation, count in provider.operations.items():
                bucket["operations"][operation] = bucket["operations"].get(operation, 0) + count
            bucket["models"].update(provider.models)
            bucket["claim_ids"].add(summary.claim_id)

    return {
        provider_name: AggregatedUsageProviderBreakdown(
            requests=payload["requests"],
            failed_requests=payload["failed_requests"],
            input_tokens=payload["input_tokens"],
            output_tokens=payload["output_tokens"],
            estimated_cost_usd=round(float(payload["estimated_cost_usd"]), 8),
            operations=dict(sorted(payload["operations"].items())),
            models=sorted(payload["models"]),
            claim_count=len(payload["claim_ids"]),
        )
        for provider_name, payload in sorted(aggregate.items())
    }


def _tenant_usage_summary(
    *,
    tenant_id: str | None,
    claims: list[ClaimRecord],
    usage_records: list[ClaimUsageSummaryRecord],
) -> TenantUsageSummary:
    claim_summaries = [_claim_usage_to_schema(record) for record in usage_records]
    return TenantUsageSummary(
        tenant_id=tenant_id,
        total_claims=len(claims),
        claims_with_usage=len(usage_records),
        claims_with_failed_external_requests=sum(
            1 for record in usage_records if record.failed_external_requests > 0
        ),
        total_external_requests=sum(record.total_external_requests for record in usage_records),
        failed_external_requests=sum(record.failed_external_requests for record in usage_records),
        total_input_tokens=sum(record.total_input_tokens for record in usage_records),
        total_output_tokens=sum(record.total_output_tokens for record in usage_records),
        estimated_cost_usd=round(
            sum(float(record.estimated_cost_usd) for record in usage_records),
            8,
        ),
        providers=_aggregate_usage_providers(claim_summaries),
    )


def get_tenant_usage_summary(tenant_id: str | None) -> TenantUsageSummary:
    with session_scope() as session:
        claim_stmt = select(ClaimRecord).order_by(
            ClaimRecord.created_at.asc(),
            ClaimRecord.claim_id.asc(),
        )
        usage_stmt = select(ClaimUsageSummaryRecord)
        if tenant_id is None:
            claim_stmt = claim_stmt.where(ClaimRecord.tenant_id.is_(None))
            usage_stmt = usage_stmt.where(ClaimUsageSummaryRecord.tenant_id.is_(None))
        else:
            claim_stmt = claim_stmt.where(ClaimRecord.tenant_id == tenant_id)
            usage_stmt = usage_stmt.where(ClaimUsageSummaryRecord.tenant_id == tenant_id)

        claims = session.execute(claim_stmt).scalars().all()
        usage_records = session.execute(usage_stmt).scalars().all()
        return _tenant_usage_summary(
            tenant_id=tenant_id,
            claims=claims,
            usage_records=usage_records,
        )


def list_tenant_usage_summaries() -> list[TenantUsageSummary]:
    with session_scope() as session:
        claims = session.execute(
            select(ClaimRecord).order_by(ClaimRecord.created_at.asc(), ClaimRecord.claim_id.asc())
        ).scalars().all()
        usage_records = session.execute(select(ClaimUsageSummaryRecord)).scalars().all()

        claims_by_tenant: dict[str | None, list[ClaimRecord]] = {}
        for claim in claims:
            claims_by_tenant.setdefault(claim.tenant_id, []).append(claim)

        usage_by_tenant: dict[str | None, list[ClaimUsageSummaryRecord]] = {}
        for record in usage_records:
            usage_by_tenant.setdefault(record.tenant_id, []).append(record)

        tenant_ids = sorted(
            set(claims_by_tenant) | set(usage_by_tenant),
            key=lambda value: (value is None, value or ""),
        )
        return [
            _tenant_usage_summary(
                tenant_id=tenant_id,
                claims=claims_by_tenant.get(tenant_id, []),
                usage_records=usage_by_tenant.get(tenant_id, []),
            )
            for tenant_id in tenant_ids
        ]


def get_claim_queue_status(claim_id: str, tenant_id: str | None = None) -> ClaimQueueStatus | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            return None
        if tenant_id is not None and record.tenant_id != tenant_id:
            return None
        return _queue_status(record) if record else None


def list_claims(
    *,
    limit: int = 20,
    needs_review: bool | None = None,
    decided: bool | None = None,
    tenant_id: str | None = None,
) -> list[ClaimListItem]:
    with session_scope() as session:
        stmt = select(ClaimRecord).order_by(ClaimRecord.created_at.desc())
        if tenant_id is not None:
            stmt = stmt.where(ClaimRecord.tenant_id == tenant_id)
        records = session.execute(stmt).scalars().all()

        items: list[ClaimListItem] = []
        for record in records:
            if needs_review is not None and bool(record.fusion_json.get("needs_review")) != needs_review:
                continue
            has_decision = record.decision_json is not None
            if decided is not None and has_decision != decided:
                continue
            decision = (
                ClaimDecision.model_validate(record.decision_json)
                if record.decision_json
                else None
            )
            items.append(
                ClaimListItem(
                    claim_id=record.claim_id,
                    tenant_id=record.tenant_id,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    status=record.status,
                    task_id=record.task_id,
                    error_message=record.error_message,
                    context=ClaimContext.model_validate(record.context_json),
                    fusion=record.fusion_json,
                    decision=decision,
                    signal_count=len(record.signals_json),
                    artifact_count=len(record.artifacts),
                )
            )
        return items[:limit]


def record_decision(
    claim_id: str, request: ClaimDecisionRequest, tenant_id: str | None = None
) -> StoredClaim | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            return None
        if tenant_id is not None and record.tenant_id != tenant_id:
            return None
        decision = ClaimDecision(
            reviewer_id=request.reviewer_id,
            decision=request.decision,
            reason=request.reason,
            decided_at=utc_now(),
        )
        record.decision_json = decision.model_dump(mode="json")
        session.flush()
        _append_audit_event(
            session,
            claim_id,
            "decision_recorded",
            {
                "reviewer_id": request.reviewer_id,
                "decision": request.decision.value,
                "reason": request.reason,
            },
        )
        session.flush()
        session.refresh(record)
        return _claim_to_schema(record)


def mark_claim_failed(claim_id: str, error_message: str) -> ClaimQueueStatus | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            return None
        record.status = ClaimStatus.FAILED.value
        record.error_message = error_message
        if record.started_at is None:
            record.started_at = utc_now()
        record.completed_at = utc_now()
        session.flush()
        _append_audit_event(
            session,
            claim_id,
            "claim_processing_failed",
            {"error_message": error_message},
        )
        session.flush()
        session.refresh(record)
        return _queue_status(record)


def get_claim_audit_events(claim_id: str, tenant_id: str | None = None) -> list[AuditEvent]:
    with session_scope() as session:
        if tenant_id is not None:
            claim = session.get(ClaimRecord, claim_id)
            if claim is None or claim.tenant_id != tenant_id:
                return []
        stmt = (
            select(AuditEventRecord)
            .where(AuditEventRecord.claim_id == claim_id)
            .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
        )
        records = session.execute(stmt).scalars().all()
        return [
            AuditEvent(
                id=record.id,
                claim_id=record.claim_id,
                event_type=record.event_type,
                payload=record.payload_json,
                created_at=record.created_at,
            )
            for record in records
        ]


def add_artifact(
    *,
    claim_id: str,
    kind: ArtifactKind,
    filename: str,
    media_type: str,
    byte_size: int,
    sha256: str,
    storage_backend: str,
    storage_key: str,
    tenant_id: str | None = None,
) -> ClaimArtifact | None:
    with session_scope() as session:
        claim = session.get(ClaimRecord, claim_id)
        if claim is None:
            return None
        if tenant_id is not None and claim.tenant_id != tenant_id:
            return None
        record = ArtifactRecord(
            claim_id=claim_id,
            kind=kind.value,
            filename=filename,
            media_type=media_type,
            byte_size=byte_size,
            sha256=sha256,
            storage_backend=storage_backend,
            storage_key=storage_key,
        )
        session.add(record)
        session.flush()
        _append_audit_event(
            session,
            claim_id,
            "artifact_stored",
            {
                "artifact_id": record.id,
                "kind": kind.value,
                "storage_backend": storage_backend,
                "byte_size": byte_size,
            },
        )
        session.flush()
        session.refresh(record)
        return _artifact_to_schema(record)


def list_claim_artifacts(claim_id: str, tenant_id: str | None = None) -> list[ClaimArtifact] | None:
    with session_scope() as session:
        claim = session.get(ClaimRecord, claim_id)
        if claim is None:
            return None
        if tenant_id is not None and claim.tenant_id != tenant_id:
            return None
        stmt = (
            select(ArtifactRecord)
            .where(ArtifactRecord.claim_id == claim_id)
            .order_by(ArtifactRecord.created_at.asc(), ArtifactRecord.id.asc())
        )
        records = session.execute(stmt).scalars().all()
        return [_artifact_to_schema(record) for record in records]


def get_artifact_record(
    claim_id: str, artifact_id: int, tenant_id: str | None = None
) -> ArtifactRecord | None:
    with session_scope() as session:
        if tenant_id is not None:
            claim = session.get(ClaimRecord, claim_id)
            if claim is None or claim.tenant_id != tenant_id:
                return None
        stmt = select(ArtifactRecord).where(
            ArtifactRecord.claim_id == claim_id, ArtifactRecord.id == artifact_id
        )
        record = session.execute(stmt).scalar_one_or_none()
        if record is None:
            return None
        session.expunge(record)
        return record


def create_tenant(
    *,
    name: str,
    slug: str | None = None,
    rate_limit_requests: int | None = None,
    rate_limit_window_seconds: int | None = None,
) -> TenantResponse:
    settings = get_settings()
    tenant_id = (slug or name.strip().lower().replace(" ", "-"))[:80] or str(uuid4())
    with session_scope() as session:
        record = TenantRecord(
            tenant_id=tenant_id,
            name=name.strip(),
            is_active=True,
            rate_limit_requests=rate_limit_requests or settings.default_tenant_rate_limit_requests,
            rate_limit_window_seconds=(
                rate_limit_window_seconds or settings.default_tenant_rate_limit_window_seconds
            ),
        )
        session.add(record)
        session.flush()
        session.refresh(record)
        return _tenant_to_schema(record)


def create_api_key(
    *,
    tenant_id: str,
    name: str,
    raw_key: str,
    key_hash: str,
    key_prefix: str,
    rate_limit_requests: int | None = None,
    rate_limit_window_seconds: int | None = None,
) -> IssuedApiKeyResponse | None:
    with session_scope() as session:
        tenant = session.get(TenantRecord, tenant_id)
        if tenant is None or not tenant.is_active:
            return None
        record = ApiKeyRecord(
            tenant_id=tenant_id,
            name=name.strip(),
            key_prefix=key_prefix,
            key_hash=key_hash,
            rate_limit_requests=rate_limit_requests or tenant.rate_limit_requests,
            rate_limit_window_seconds=(
                rate_limit_window_seconds or tenant.rate_limit_window_seconds
            ),
        )
        session.add(record)
        session.flush()
        session.refresh(record)
        return IssuedApiKeyResponse(
            api_key_id=record.id,
            tenant_id=record.tenant_id,
            name=record.name,
            key_prefix=record.key_prefix,
            api_key=raw_key,
            rate_limit_requests=record.rate_limit_requests,
            rate_limit_window_seconds=record.rate_limit_window_seconds,
            created_at=record.created_at,
        )


def get_api_key_auth(key_hash: str) -> dict[str, Any] | None:
    with session_scope() as session:
        stmt = (
            select(ApiKeyRecord, TenantRecord)
            .join(TenantRecord, ApiKeyRecord.tenant_id == TenantRecord.tenant_id)
            .where(
                ApiKeyRecord.key_hash == key_hash,
                ApiKeyRecord.is_active.is_(True),
                TenantRecord.is_active.is_(True),
            )
        )
        row = session.execute(stmt).one_or_none()
        if row is None:
            return None
        api_key, tenant = row
        return {
            "api_key_id": api_key.id,
            "tenant_id": tenant.tenant_id,
            "tenant_name": tenant.name,
            "rate_limit_requests": api_key.rate_limit_requests,
            "rate_limit_window_seconds": api_key.rate_limit_window_seconds,
        }


def touch_api_key_last_used(api_key_id: int) -> None:
    with session_scope() as session:
        record = session.get(ApiKeyRecord, api_key_id)
        if record is None:
            return
        record.last_used_at = utc_now()


def get_rate_limit_state(
    *, scope_type: str, scope_key: str, window_seconds: int
) -> tuple[int, datetime | None]:
    since = utc_now() - timedelta(seconds=window_seconds)
    with session_scope() as session:
        stmt = select(
            func.count(RateLimitEventRecord.id),
            func.min(RateLimitEventRecord.created_at),
        ).where(
            RateLimitEventRecord.scope_type == scope_type,
            RateLimitEventRecord.scope_key == scope_key,
            RateLimitEventRecord.created_at >= since,
        )
        count, oldest = session.execute(stmt).one()
        return int(count or 0), oldest


def record_rate_limit_hit(
    *,
    scope_type: str,
    scope_key: str,
    route: str,
    tenant_id: str | None = None,
    api_key_id: int | None = None,
) -> None:
    with session_scope() as session:
        session.add(
            RateLimitEventRecord(
                scope_type=scope_type,
                scope_key=scope_key,
                route=route,
                tenant_id=tenant_id,
                api_key_id=api_key_id,
            )
        )


def get_original_artifact_record(claim_id: str) -> ArtifactRecord | None:
    with session_scope() as session:
        stmt = (
            select(ArtifactRecord)
            .where(
                ArtifactRecord.claim_id == claim_id,
                ArtifactRecord.kind == ArtifactKind.ORIGINAL_UPLOAD.value,
            )
            .order_by(ArtifactRecord.created_at.asc(), ArtifactRecord.id.asc())
        )
        record = session.execute(stmt).scalar_one_or_none()
        if record is None:
            return None
        session.expunge(record)
        return record


def get_recent_original_artifact_records(
    *, exclude_claim_id: str, limit: int
) -> list[ArtifactRecord]:
    with session_scope() as session:
        stmt = (
            select(ArtifactRecord)
            .where(
                ArtifactRecord.claim_id != exclude_claim_id,
                ArtifactRecord.kind == ArtifactKind.ORIGINAL_UPLOAD.value,
            )
            .order_by(ArtifactRecord.created_at.desc(), ArtifactRecord.id.desc())
            .limit(limit)
        )
        records = session.execute(stmt).scalars().all()
        for record in records:
            session.expunge(record)
        return records
