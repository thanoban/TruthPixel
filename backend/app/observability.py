from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from uuid import uuid4


TRACE_HEADER = "X-Trace-Id"

_trace_id_var: ContextVar[str | None] = ContextVar("truthpixel_trace_id", default=None)
_claim_id_var: ContextVar[str | None] = ContextVar("truthpixel_claim_id", default=None)
_tenant_id_var: ContextVar[str | None] = ContextVar("truthpixel_tenant_id", default=None)
_usage_summary_var: ContextVar[dict | None] = ContextVar("truthpixel_usage_summary", default=None)
_SAFE_LABEL_RE = re.compile(r"[^a-z0-9._:/+-]+")
_MAX_PROVIDER_LABEL_LENGTH = 40
_MAX_OPERATION_LABEL_LENGTH = 60
_MAX_MODEL_LABEL_LENGTH = 120
_MAX_MODELS_PER_PROVIDER = 12


def ensure_trace_id(existing: str | None = None) -> str:
    trace_id = existing or uuid4().hex
    _trace_id_var.set(trace_id)
    return trace_id


def get_trace_id() -> str | None:
    return _trace_id_var.get()


def bind_claim_context(*, claim_id: str | None = None, tenant_id: str | None = None) -> None:
    if claim_id is not None:
        _claim_id_var.set(claim_id)
    if tenant_id is not None:
        _tenant_id_var.set(tenant_id)


def clear_context() -> None:
    _trace_id_var.set(None)
    _claim_id_var.set(None)
    _tenant_id_var.set(None)
    _usage_summary_var.set(None)


def context_fields() -> dict[str, str]:
    fields: dict[str, str] = {}
    trace_id = _trace_id_var.get()
    claim_id = _claim_id_var.get()
    tenant_id = _tenant_id_var.get()
    if trace_id:
        fields["trace_id"] = trace_id
    if claim_id:
        fields["claim_id"] = claim_id
    if tenant_id:
        fields["tenant_id"] = tenant_id
    return fields


def _fresh_usage_summary() -> dict:
    return {
        "total_external_requests": 0,
        "failed_external_requests": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "providers": {},
    }


def _safe_usage_label(value: str, *, fallback: str, max_length: int) -> str:
    normalized = (value or "").strip().lower()
    normalized = _SAFE_LABEL_RE.sub("_", normalized).strip("._:-/+")
    if not normalized:
        normalized = fallback
    return normalized[:max_length]


def record_external_usage(
    *,
    provider: str,
    operation: str,
    model: str = "",
    request_count: int = 1,
    failed: bool = False,
    input_tokens: int = 0,
    output_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
) -> None:
    safe_provider = _safe_usage_label(
        provider,
        fallback="unknown_provider",
        max_length=_MAX_PROVIDER_LABEL_LENGTH,
    )
    safe_operation = _safe_usage_label(
        operation,
        fallback="unknown_operation",
        max_length=_MAX_OPERATION_LABEL_LENGTH,
    )
    safe_model = _safe_usage_label(
        model,
        fallback="",
        max_length=_MAX_MODEL_LABEL_LENGTH,
    )
    summary = _usage_summary_var.get()
    if summary is None:
        summary = _fresh_usage_summary()
        _usage_summary_var.set(summary)

    summary["total_external_requests"] += max(0, int(request_count))
    summary["failed_external_requests"] += max(0, int(request_count)) if failed else 0
    summary["total_input_tokens"] += max(0, int(input_tokens))
    summary["total_output_tokens"] += max(0, int(output_tokens))
    summary["estimated_cost_usd"] = round(
        float(summary["estimated_cost_usd"]) + max(0.0, float(estimated_cost_usd)),
        8,
    )

    provider_bucket = summary["providers"].setdefault(
        safe_provider,
        {
            "requests": 0,
            "failed_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost_usd": 0.0,
            "operations": {},
            "models": [],
        },
    )
    provider_bucket["requests"] += max(0, int(request_count))
    provider_bucket["failed_requests"] += max(0, int(request_count)) if failed else 0
    provider_bucket["input_tokens"] += max(0, int(input_tokens))
    provider_bucket["output_tokens"] += max(0, int(output_tokens))
    provider_bucket["estimated_cost_usd"] = round(
        float(provider_bucket["estimated_cost_usd"]) + max(0.0, float(estimated_cost_usd)),
        8,
    )
    provider_bucket["operations"][safe_operation] = (
        provider_bucket["operations"].get(safe_operation, 0) + max(0, int(request_count))
    )
    if (
        safe_model
        and safe_model not in provider_bucket["models"]
        and len(provider_bucket["models"]) < _MAX_MODELS_PER_PROVIDER
    ):
        provider_bucket["models"].append(safe_model)


def usage_summary_fields() -> dict:
    summary = _usage_summary_var.get() or _fresh_usage_summary()
    providers: dict[str, dict] = {}
    for name, payload in summary["providers"].items():
        providers[name] = {
            "requests": payload["requests"],
            "failed_requests": payload["failed_requests"],
            "input_tokens": payload["input_tokens"],
            "output_tokens": payload["output_tokens"],
            "estimated_cost_usd": round(float(payload["estimated_cost_usd"]), 8),
            "operations": dict(sorted(payload["operations"].items())),
            "models": sorted(payload["models"]),
        }
    return {
        "total_external_requests": summary["total_external_requests"],
        "failed_external_requests": summary["failed_external_requests"],
        "total_input_tokens": summary["total_input_tokens"],
        "total_output_tokens": summary["total_output_tokens"],
        "estimated_cost_usd": round(float(summary["estimated_cost_usd"]), 8),
        "providers": dict(sorted(providers.items())),
    }


def persist_usage_summary(
    *,
    outcome: str = "",
    reason: str = "",
) -> None:
    fields = context_fields()
    claim_id = fields.get("claim_id")
    if not claim_id:
        return

    from .storage import upsert_claim_usage_summary

    upsert_claim_usage_summary(
        claim_id=claim_id,
        tenant_id=fields.get("tenant_id"),
        outcome=(outcome or reason or "unknown")[:40],
        summary=usage_summary_fields(),
    )


def log_event(logger: logging.Logger, event: str, **fields) -> None:
    payload = {"event": event, **context_fields(), **fields}
    logger.info(json.dumps(payload, sort_keys=True, default=str))


def log_usage_summary(logger: logging.Logger, event: str = "claim_usage_summary", **fields) -> None:
    persist_usage_summary(
        outcome=str(fields.get("outcome", "")),
        reason=str(fields.get("reason", "")),
    )
    log_event(logger, event, **usage_summary_fields(), **fields)
