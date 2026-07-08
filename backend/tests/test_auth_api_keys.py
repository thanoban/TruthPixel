import io

from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.main import app
from app.storage import reset_storage_state


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
