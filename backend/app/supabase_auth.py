from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient

from .config import get_settings


class SupabaseAuthError(Exception):
    """Raised when a bearer token can't be verified as a live Supabase Auth session."""


class SupabaseAuthNotConfigured(SupabaseAuthError):
    """Raised when this backend deployment hasn't set SUPABASE_URL at all.

    Deliberately a distinct type from SupabaseAuthError: a caller (auth.py) needs to treat
    "we never configured Supabase verification here" differently from "this specific token
    is invalid" — the former should fall back to anonymous rate limiting (the frontend has
    no way to know the backend's config), the latter should 401. Conflating them would mean
    a signed-in webapp user on an unconfigured backend gets a confusing 401 instead of just
    the anonymous limit they'd have gotten without ever logging in.
    """


@lru_cache(maxsize=4)
def _jwk_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def verify_supabase_token(token: str) -> dict:
    """Verify a Supabase Auth access token (webapp login) via the project's JWKS endpoint.

    Supabase signs Auth JWTs asymmetrically (RS256/ES256) — PyJWKClient fetches and caches
    the project's public signing keys, so no shared secret needs to live in this backend's
    config. Raises SupabaseAuthNotConfigured when SUPABASE_URL is unset, or SupabaseAuthError
    for any other failure (expired, wrong audience, bad signature, JWKS unreachable) —
    callers should treat the latter as "not a valid session," not distinguish the reason to
    the client.
    """
    settings = get_settings()
    jwks_url = settings.resolved_supabase_jwks_url
    if not jwks_url:
        raise SupabaseAuthNotConfigured("Supabase auth not configured (SUPABASE_URL unset)")

    try:
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except Exception as exc:  # jwt.PyJWTError subclasses, urllib/network errors, etc.
        raise SupabaseAuthError(str(exc)) from exc

    return payload
