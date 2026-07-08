import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.jobs import reset_job_state
from app.main import app
from app.storage import get_claim_audit_events, reset_storage_state
from app.trufor import TruForResult


def make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (25, 160, 80)).save(buf, format="JPEG")
    return buf.getvalue()


def make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (32, 32), (255, 80, 0, 180)).save(buf, format="PNG")
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
    monkeypatch.setenv("L2_TRUFOR_REPO_DIR", "D:/fake/trufor")
    monkeypatch.setenv("L2_TRUFOR_MODEL_FILE", "D:/fake/trufor/model.pth.tar")
    monkeypatch.setattr("app.jobs.httpx.post", fake_post)
    monkeypatch.setattr(
        "app.analyzers.l2_forensics.run_trufor_inference",
        lambda image: TruForResult(
            score=0.79,
            confidence=0.67,
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
        assert len(claim_payload["artifacts"]) == 2

        l2_signal = next(signal for signal in claim_payload["signals"] if signal["layer"] == "l2_forensics")
        assert l2_signal["evidence"]["provider"] == "trufor"
        assert l2_signal["evidence"]["heatmap_available"] is True

        audit = [event.event_type for event in get_claim_audit_events(claim_id)]
        assert audit == [
            "claim_queued",
            "artifact_stored",
            "claim_processing_started",
            "artifact_stored",
            "claim_persisted",
        ]

    assert len(webhook_calls) == 1
    assert webhook_calls[0][0] == "https://example.com/webhook"
    assert webhook_calls[0][1]["claim_id"] == claim_id

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()
