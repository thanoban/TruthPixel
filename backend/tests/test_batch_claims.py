import io
import json

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.jobs import reset_job_state
from app.main import app
from app.storage import reset_storage_state
from app.trufor import TruForResult


def make_jpeg(color) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
    return buf.getvalue()


def make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (32, 32), (255, 80, 0, 180)).save(buf, format="PNG")
    return buf.getvalue()


def test_batch_claim_queue_completes_in_eager_mode(monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-batch.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-secret")
    monkeypatch.setenv("L2_TRUFOR_REPO_DIR", "D:/fake/trufor")
    monkeypatch.setenv("L2_TRUFOR_MODEL_FILE", "D:/fake/trufor/model.pth.tar")
    monkeypatch.setattr(
        "app.analyzers.l2_forensics.run_trufor_inference",
        lambda image: TruForResult(
            score=0.81,
            confidence=0.68,
            anomaly_map=np.array([[0.2, 0.7], [0.1, 0.9]], dtype=np.float32),
            confidence_map=np.array([[0.8, 0.6], [0.7, 0.9]], dtype=np.float32),
            heatmap_png=make_png(),
            heatmap_mean=0.41,
            heatmap_max=0.9,
            confidence_mean=0.75,
            suspicious_pixel_fraction=0.28,
            model_version="trufor:test-weights.pth.tar",
        ),
    )
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()

    with TestClient(app) as client:
        tenant_response = client.post(
            "/v1/admin/tenants",
            headers={"X-Admin-Token": "admin-secret"},
            json={"name": "Batch Tenant", "slug": "batch-tenant"},
        )
        assert tenant_response.status_code == 201
        tenant_id = tenant_response.json()["tenant_id"]

        key_response = client.post(
            f"/v1/admin/tenants/{tenant_id}/api-keys",
            headers={"X-Admin-Token": "admin-secret"},
            json={"name": "batch-key"},
        )
        assert key_response.status_code == 201
        api_key = key_response.json()["api_key"]

        items = [
            {
                "order_id": "ORD-B1",
                "product_sku": "SKU-1",
                "claim_reason": "scratched",
                "listing_image_urls": ["https://example.com/listing-1.jpg"],
                "webhook_url": "https://example.com/webhook-1",
            },
            {
                "order_id": "ORD-B2",
                "product_sku": "SKU-2",
                "claim_reason": "broken",
                "listing_image_urls": [],
                "webhook_url": "",
            },
        ]
        response = client.post(
            "/v1/claims/batch",
            headers={"X-API-Key": api_key},
            files=[
                ("images", ("one.jpg", make_jpeg((25, 160, 80)), "image/jpeg")),
                ("images", ("two.jpg", make_jpeg((80, 40, 180)), "image/jpeg")),
            ],
            data={"items_json": json.dumps(items)},
        )
        assert response.status_code == 202
        payload = response.json()
        assert payload["count"] == 2
        assert len(payload["claims"]) == 2

        first_claim_id = payload["claims"][0]["claim_id"]
        second_claim_id = payload["claims"][1]["claim_id"]

        first_claim = client.get(
            f"/v1/claims/{first_claim_id}",
            headers={"X-API-Key": api_key},
        )
        assert first_claim.status_code == 200
        first_body = first_claim.json()
        assert first_body["status"] == "completed"
        assert first_body["context"]["order_id"] == "ORD-B1"
        assert first_body["context"]["listing_image_urls"] == ["https://example.com/listing-1.jpg"]

        second_claim = client.get(
            f"/v1/claims/{second_claim_id}",
            headers={"X-API-Key": api_key},
        )
        assert second_claim.status_code == 200
        second_body = second_claim.json()
        assert second_body["status"] == "completed"
        assert second_body["context"]["order_id"] == "ORD-B2"

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()


def test_batch_claim_queue_rejects_count_mismatch(monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-batch-mismatch.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-secret")
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()

    with TestClient(app) as client:
        tenant_response = client.post(
            "/v1/admin/tenants",
            headers={"X-Admin-Token": "admin-secret"},
            json={"name": "Batch Tenant", "slug": "batch-mismatch"},
        )
        tenant_id = tenant_response.json()["tenant_id"]
        key_response = client.post(
            f"/v1/admin/tenants/{tenant_id}/api-keys",
            headers={"X-Admin-Token": "admin-secret"},
            json={"name": "batch-key"},
        )
        api_key = key_response.json()["api_key"]

        response = client.post(
            "/v1/claims/batch",
            headers={"X-API-Key": api_key},
            files=[
                ("images", ("one.jpg", make_jpeg((25, 160, 80)), "image/jpeg")),
                ("images", ("two.jpg", make_jpeg((80, 40, 180)), "image/jpeg")),
            ],
            data={"items_json": json.dumps([{"order_id": "ORD-B1"}])},
        )
        assert response.status_code == 400
        assert "must match uploaded image count" in response.json()["detail"]

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()
