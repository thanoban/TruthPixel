from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Header, HTTPException, Request, Response, status

from .config import get_settings
from .storage import (
    get_api_key_auth,
    get_rate_limit_state,
    record_rate_limit_hit,
    touch_api_key_last_used,
)


API_KEY_HEADER = "X-API-Key"
ADMIN_TOKEN_HEADER = "X-Admin-Token"


@dataclass
class AuthContext:
    tenant_id: str | None
    tenant_name: str | None
    api_key_id: int | None = None
    is_public: bool = False


def generate_api_key() -> str:
    return f"tpk_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def key_prefix(raw_key: str) -> str:
    return raw_key[:12]


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _set_rate_limit_headers(response: Response, *, limit: int, remaining: int, retry_after: int) -> None:
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
    response.headers["Retry-After"] = str(max(retry_after, 0))


def _enforce_rate_limit(
    *,
    response: Response,
    scope_type: str,
    scope_key: str,
    limit: int,
    window_seconds: int,
    route: str,
    tenant_id: str | None = None,
    api_key_id: int | None = None,
) -> None:
    count, oldest = get_rate_limit_state(
        scope_type=scope_type,
        scope_key=scope_key,
        window_seconds=window_seconds,
    )
    now = datetime.now(timezone.utc)
    if count >= limit:
        retry_after = window_seconds
        if oldest is not None:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            elapsed = max(0, int((now - oldest).total_seconds()))
            retry_after = max(1, window_seconds - elapsed)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )

    record_rate_limit_hit(
        scope_type=scope_type,
        scope_key=scope_key,
        route=route,
        tenant_id=tenant_id,
        api_key_id=api_key_id,
    )
    remaining = max(0, limit - (count + 1))
    _set_rate_limit_headers(response, limit=limit, remaining=remaining, retry_after=0)


def require_admin_token(x_admin_token: str | None = Header(default=None, alias=ADMIN_TOKEN_HEADER)) -> None:
    settings = get_settings()
    if not settings.admin_api_token:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="admin API disabled")
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")


def _authenticate_api_key(raw_key: str | None) -> AuthContext:
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")
    auth = get_api_key_auth(hash_api_key(raw_key))
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    touch_api_key_last_used(auth["api_key_id"])
    return AuthContext(
        tenant_id=auth["tenant_id"],
        tenant_name=auth["tenant_name"],
        api_key_id=auth["api_key_id"],
    )


def require_tenant_api_key(
    request: Request,
    response: Response,
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> AuthContext:
    settings = get_settings()
    if not settings.api_auth_enabled:
        return AuthContext(tenant_id="local-dev", tenant_name="Local Dev")

    auth = _authenticate_api_key(x_api_key)
    record = get_api_key_auth(hash_api_key(x_api_key or ""))
    assert record is not None
    _enforce_rate_limit(
        response=response,
        scope_type="api_key",
        scope_key=str(auth.api_key_id),
        limit=record["rate_limit_requests"],
        window_seconds=record["rate_limit_window_seconds"],
        route=request.url.path,
        tenant_id=auth.tenant_id,
        api_key_id=auth.api_key_id,
    )
    return auth


def allow_public_submission(
    request: Request,
    response: Response,
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> AuthContext:
    settings = get_settings()
    if not settings.api_auth_enabled:
        return AuthContext(tenant_id="local-dev", tenant_name="Local Dev")

    if x_api_key:
        return require_tenant_api_key(request=request, response=response, x_api_key=x_api_key)

    if not settings.public_submission_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API key required")

    client_ip = _client_ip(request)
    _enforce_rate_limit(
        response=response,
        scope_type="public_ip",
        scope_key=client_ip,
        limit=settings.public_rate_limit_requests,
        window_seconds=settings.public_rate_limit_window_seconds,
        route=request.url.path,
    )
    return AuthContext(tenant_id=None, tenant_name="Public Webapp", is_public=True)
