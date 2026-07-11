from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from .config import get_settings


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))


def _token_secret() -> str:
    settings = get_settings()
    secret = settings.artifact_access_token_secret or settings.admin_api_token
    if not secret and not settings.api_auth_enabled:
        secret = "local-dev-artifact-access"
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="artifact access tokens are not configured",
        )
    return secret


def create_artifact_access_token(
    *,
    claim_id: str,
    artifact_id: int,
    tenant_id: str | None,
) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = int(time.time()) + settings.artifact_access_token_ttl_seconds
    payload: dict[str, Any] = {
        "claim_id": claim_id,
        "artifact_id": artifact_id,
        "tenant_id": tenant_id,
        "exp": expires_at,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _b64_encode(payload_bytes)
    signature = hmac.new(
        _token_secret().encode("utf-8"),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_b64_encode(signature)}", datetime.fromtimestamp(expires_at, timezone.utc)


def verify_artifact_access_token(token: str) -> dict[str, Any]:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid artifact token") from exc

    expected_signature = hmac.new(
        _token_secret().encode("utf-8"),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        provided_signature = _b64_decode(signature_part)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid artifact token") from exc
    if not hmac.compare_digest(provided_signature, expected_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid artifact token")

    try:
        payload = json.loads(_b64_decode(payload_part))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid artifact token") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="artifact token expired")
    if not isinstance(payload.get("claim_id"), str) or not isinstance(payload.get("artifact_id"), int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid artifact token")
    if payload.get("tenant_id") is not None and not isinstance(payload.get("tenant_id"), str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid artifact token")
    return payload
