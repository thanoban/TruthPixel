from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from uuid import uuid4


TRACE_HEADER = "X-Trace-Id"

_trace_id_var: ContextVar[str | None] = ContextVar("truthpixel_trace_id", default=None)
_claim_id_var: ContextVar[str | None] = ContextVar("truthpixel_claim_id", default=None)
_tenant_id_var: ContextVar[str | None] = ContextVar("truthpixel_tenant_id", default=None)


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


def log_event(logger: logging.Logger, event: str, **fields) -> None:
    payload = {"event": event, **context_fields(), **fields}
    logger.info(json.dumps(payload, sort_keys=True, default=str))
