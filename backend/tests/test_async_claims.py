import io

from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.jobs import reset_job_state
from app.main import app
from app.storage import get_claim_audit_events, reset_storage_state


def make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (25, 160, 80)).save(buf, format="JPEG")
    return buf.getvalue()


def test_async_claim_queue_completes_in_eager_mode(monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-async.db"
    artifact_dir = tmp_path / "artifacts"
    webhook_calls: list[tuple[str, dict]] = []

    def fake_post(url, json, timeout):
        webhook_calls.append((url, json))

        class FakeResponse:
            def raise_for_status(self):
                return None

        return FakeResponse()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "true")
    monkeypatch.setattr("app.jobs.httpx.post", fake_post)
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()

    with TestClient(app) as client:
        response = client.post(
            "/v1/claims/async",
            files={"image": ("queued.jpg", make_jpeg(), "image/jpeg")},
            data={
                "order_id": "ORD-ASYNC",
                "product_sku": "SKU-Q",
                "claim_reason": "scratched",
                "webhook_url": "https://example.com/webhook",
            },
        )
        assert response.status_code == 202
        queued = response.json()
        claim_id = queued["claim_id"]
        assert queued["status"] in {"pending", "completed"}
        assert queued["task_id"]

        status_response = client.get(f"/v1/claims/{claim_id}/status")
        assert status_response.status_code == 200
        status_payload = status_response.json()
        assert status_payload["status"] == "completed"
        assert status_payload["completed_at"] is not None

        claim_response = client.get(f"/v1/claims/{claim_id}")
        assert claim_response.status_code == 200
        claim_payload = claim_response.json()
        assert claim_payload["status"] == "completed"
        assert claim_payload["context"]["order_id"] == "ORD-ASYNC"
        assert len(claim_payload["signals"]) == 5

        audit = [event.event_type for event in get_claim_audit_events(claim_id)]
        assert audit == [
            "claim_queued",
            "artifact_stored",
            "claim_processing_started",
            "claim_persisted",
        ]

    assert len(webhook_calls) == 1
    assert webhook_calls[0][0] == "https://example.com/webhook"
    assert webhook_calls[0][1]["claim_id"] == claim_id

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()
