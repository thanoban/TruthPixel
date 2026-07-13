import io

from fastapi.testclient import TestClient
from PIL import Image

import app.auth as auth_module
from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.main import app
from app.storage import reset_storage_state
from app.supabase_auth import SupabaseAuthError, SupabaseAuthNotConfigured


def make_jpeg(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 50, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def configure_auth_env(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "truthpixel-auth.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-secret")
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def create_tenant_and_key(client: TestClient, tenant_name: str, key_name: str) -> tuple[dict, str]:
    tenant_response = client.post(
        "/v1/admin/tenants",
        headers={"X-Admin-Token": "admin-secret"},
        json={"name": tenant_name, "slug": tenant_name.lower().replace(" ", "-")},
    )
    assert tenant_response.status_code == 201
    tenant = tenant_response.json()
    key_response = client.post(
        f"/v1/admin/tenants/{tenant['tenant_id']}/api-keys",
        headers={"X-Admin-Token": "admin-secret"},
        json={"name": key_name},
    )
    assert key_response.status_code == 201
    return tenant, key_response.json()["api_key"]


def test_tenant_api_keys_protect_claim_routes(monkeypatch, tmp_path):
    configure_auth_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        tenant_a, key_a = create_tenant_and_key(client, "Tenant A", "primary")
        tenant_b, key_b = create_tenant_and_key(client, "Tenant B", "primary")

        create_response = client.post(
            "/v1/claims",
            headers={"X-API-Key": key_a},
            files={"image": ("tenant-a.jpg", make_jpeg(), "image/jpeg")},
            data={"order_id": "ORD-A", "product_sku": "SKU-A", "claim_reason": "damage"},
        )
        assert create_response.status_code == 200
        created = create_response.json()
        assert created["tenant_id"] == tenant_a["tenant_id"]
        claim_id = created["claim_id"]

        fetch_response = client.get(f"/v1/claims/{claim_id}", headers={"X-API-Key": key_a})
        assert fetch_response.status_code == 200
        assert fetch_response.json()["claim_id"] == claim_id

        foreign_fetch = client.get(f"/v1/claims/{claim_id}", headers={"X-API-Key": key_b})
        assert foreign_fetch.status_code == 404
        assert tenant_b["tenant_id"] != tenant_a["tenant_id"]

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def test_api_key_rate_limit_returns_429(monkeypatch, tmp_path):
    configure_auth_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        tenant_response = client.post(
            "/v1/admin/tenants",
            headers={"X-Admin-Token": "admin-secret"},
            json={
                "name": "Rate Limited Tenant",
                "slug": "rate-limited-tenant",
                "rate_limit_requests": 2,
                "rate_limit_window_seconds": 3600,
            },
        )
        assert tenant_response.status_code == 201
        tenant_id = tenant_response.json()["tenant_id"]
        key_response = client.post(
            f"/v1/admin/tenants/{tenant_id}/api-keys",
            headers={"X-Admin-Token": "admin-secret"},
            json={"name": "limited-key"},
        )
        api_key = key_response.json()["api_key"]

        create_response = client.post(
            "/v1/claims",
            headers={"X-API-Key": api_key},
            files={"image": ("rate-limit.jpg", make_jpeg(), "image/jpeg")},
            data={"order_id": "ORD-RATE"},
        )
        assert create_response.status_code == 200
        claim_id = create_response.json()["claim_id"]

        second_response = client.get(f"/v1/claims/{claim_id}", headers={"X-API-Key": api_key})
        assert second_response.status_code == 200

        limited_response = client.get(f"/v1/claims/{claim_id}", headers={"X-API-Key": api_key})
        assert limited_response.status_code == 429
        assert limited_response.json()["detail"] == "rate limit exceeded"
        assert limited_response.headers["X-RateLimit-Remaining"] == "0"

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def test_public_submission_throttle_is_optional_and_limited(monkeypatch, tmp_path):
    configure_auth_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PUBLIC_SUBMISSION_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_WINDOW_SECONDS", "3600")
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()

    with TestClient(app) as client:
        public_create = client.post(
            "/v1/claims",
            files={"image": ("public.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "public-check"},
        )
        assert public_create.status_code == 200
        assert public_create.json()["tenant_id"] is None

        second_public_create = client.post(
            "/v1/claims",
            files={"image": ("public-2.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "public-check-2"},
        )
        assert second_public_create.status_code == 429

        protected_listing = client.get("/v1/claims")
        assert protected_listing.status_code == 401

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def test_public_submission_with_supabase_session_uses_higher_user_limit(monkeypatch, tmp_path):
    # A signed-in webapp user (Google/email via Supabase Auth) is rate-limited by their
    # Supabase user id, separately from the anonymous IP bucket — see auth.py's
    # allow_public_submission. Real JWKS verification isn't exercised here (that's
    # supabase_auth.py's own concern); this test monkeypatches verify_supabase_token at the
    # point auth.py calls it, matching this suite's established pattern.
    configure_auth_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PUBLIC_SUBMISSION_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_WINDOW_SECONDS", "3600")
    monkeypatch.setenv("PUBLIC_USER_RATE_LIMIT_REQUESTS", "2")
    monkeypatch.setenv("PUBLIC_USER_RATE_LIMIT_WINDOW_SECONDS", "3600")
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()

    monkeypatch.setattr(
        auth_module,
        "verify_supabase_token",
        lambda token: {"sub": "supabase-user-123", "email": "reviewer@example.com"},
    )

    with TestClient(app) as client:
        # Anonymous IP path is capped at 1 — confirms the bearer-token path is separate,
        # not just a higher ceiling on the same bucket.
        anon_create = client.post(
            "/v1/claims",
            files={"image": ("anon.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "anon-check"},
        )
        assert anon_create.status_code == 200

        anon_throttled = client.post(
            "/v1/claims",
            files={"image": ("anon-2.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "anon-check-2"},
        )
        assert anon_throttled.status_code == 429

        headers = {"Authorization": "Bearer fake-supabase-jwt"}
        first_user_create = client.post(
            "/v1/claims",
            headers=headers,
            files={"image": ("user.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "user-check"},
        )
        assert first_user_create.status_code == 200
        assert first_user_create.json()["tenant_id"] is None

        second_user_create = client.post(
            "/v1/claims",
            headers=headers,
            files={"image": ("user-2.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "user-check-2"},
        )
        assert second_user_create.status_code == 200

        third_user_create = client.post(
            "/v1/claims",
            headers=headers,
            files={"image": ("user-3.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "user-check-3"},
        )
        assert third_user_create.status_code == 429

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def test_public_submission_rejects_invalid_supabase_token(monkeypatch, tmp_path):
    configure_auth_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PUBLIC_SUBMISSION_ENABLED", "true")
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()

    def _raise(token: str):
        raise SupabaseAuthError("signature verification failed")

    monkeypatch.setattr(auth_module, "verify_supabase_token", _raise)

    with TestClient(app) as client:
        response = client.post(
            "/v1/claims",
            headers={"Authorization": "Bearer garbage"},
            files={"image": ("bad-token.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "bad-token-check"},
        )
        assert response.status_code == 401

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def test_public_submission_falls_back_to_anonymous_when_supabase_unconfigured(monkeypatch, tmp_path):
    # A signed-in webapp user sends a bearer token, but this backend deployment never set
    # SUPABASE_URL — the frontend has no way to know that in advance. Must fall back to the
    # anonymous IP limit, not 401: a logged-in user should never get a worse outcome than an
    # anonymous one just because the backend's auth verification isn't wired up yet.
    configure_auth_env(monkeypatch, tmp_path)
    monkeypatch.setenv("PUBLIC_SUBMISSION_ENABLED", "true")
    monkeypatch.setenv("PUBLIC_RATE_LIMIT_REQUESTS", "1")
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()

    def _raise(token: str):
        raise SupabaseAuthNotConfigured("SUPABASE_URL unset")

    monkeypatch.setattr(auth_module, "verify_supabase_token", _raise)

    with TestClient(app) as client:
        response = client.post(
            "/v1/claims",
            headers={"Authorization": "Bearer whatever"},
            files={"image": ("unconfigured.jpg", make_jpeg(), "image/jpeg")},
            data={"claim_reason": "unconfigured-check"},
        )
        assert response.status_code == 200
        assert response.json()["tenant_id"] is None

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
