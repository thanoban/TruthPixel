import io
import json

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.jobs import reset_job_state
from app.main import app
from app.observability import TRACE_HEADER
from app.storage import reset_storage_state
from app.trufor import TruForResult


def make_jpeg(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (40, 150, 210)).save(buf, format="JPEG")
    return buf.getvalue()


def make_png(size=(32, 32), color=(255, 80, 0, 180)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


def parse_json_logs(caplog, logger_name: str) -> list[dict]:
    events: list[dict] = []
    for record in caplog.records:
        if record.name != logger_name:
            continue
        try:
            events.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            continue
    return events


def test_health_echoes_trace_header(caplog):
    caplog.set_level("INFO", logger="app.main")

    with TestClient(app) as client:
        response = client.get("/health", headers={TRACE_HEADER: "trace-health-123"})

    assert response.status_code == 200
    assert response.headers[TRACE_HEADER] == "trace-health-123"

    events = parse_json_logs(caplog, "app.main")
    request_completed = next(event for event in events if event["event"] == "request_completed")
    assert request_completed["trace_id"] == "trace-health-123"
    assert request_completed["path"] == "/health"
    assert request_completed["status_code"] == 200


def test_claim_sync_logs_lifecycle_with_trace(caplog, monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-observability.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    monkeypatch.setenv("L2_TRUFOR_REPO_DIR", "D:/fake/trufor")
    monkeypatch.setenv("L2_TRUFOR_MODEL_FILE", "D:/fake/trufor/model.pth.tar")
    monkeypatch.setattr(
        "app.analyzers.l2_forensics.run_trufor_inference",
        lambda image: TruForResult(
            score=0.83,
            confidence=0.7,
            anomaly_map=np.array([[0.1, 0.8], [0.2, 0.9]], dtype=np.float32),
            confidence_map=np.array([[0.7, 0.8], [0.6, 0.9]], dtype=np.float32),
            heatmap_png=make_png(),
            heatmap_mean=0.43,
            heatmap_max=0.91,
            confidence_mean=0.75,
            suspicious_pixel_fraction=0.29,
            model_version="trufor:test-weights.pth.tar",
        ),
    )
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()
    caplog.set_level("INFO", logger="app.main")

    with TestClient(app) as client:
        response = client.post(
            "/v1/claims",
            headers={TRACE_HEADER: "trace-sync-456"},
            files={"image": ("sample.jpg", make_jpeg(), "image/jpeg")},
            data={"order_id": "ORD-OBS", "product_sku": "SKU-OBS", "claim_reason": "damaged"},
        )

    assert response.status_code == 200
    claim_id = response.json()["claim_id"]

    events = parse_json_logs(caplog, "app.main")
    sync_started = next(event for event in events if event["event"] == "claim_sync_started")
    sync_completed = next(event for event in events if event["event"] == "claim_sync_completed")
    request_completed = next(event for event in events if event["event"] == "request_completed")

    assert sync_started["trace_id"] == "trace-sync-456"
    assert sync_completed["trace_id"] == "trace-sync-456"
    assert request_completed["trace_id"] == "trace-sync-456"
    assert sync_started["claim_id"] == claim_id
    assert sync_completed["claim_id"] == claim_id
    assert sync_completed["signal_count"] == 5
    assert request_completed["path"] == "/v1/claims"
    assert response.headers[TRACE_HEADER] == "trace-sync-456"

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()


def test_async_claim_logs_worker_lifecycle(caplog, monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-observability-async.db"
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
            score=0.78,
            confidence=0.66,
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
    caplog.set_level("INFO", logger="app.main")
    caplog.set_level("INFO", logger="app.jobs")

    with TestClient(app) as client:
        response = client.post(
            "/v1/claims/async",
            headers={TRACE_HEADER: "trace-async-789"},
            files={"image": ("queued.jpg", make_jpeg(), "image/jpeg")},
            data={
                "order_id": "ORD-ASYNC-OBS",
                "product_sku": "SKU-ASYNC",
                "claim_reason": "scratched",
                "webhook_url": "https://example.com/webhook",
            },
        )

    assert response.status_code == 202
    claim_id = response.json()["claim_id"]
    assert response.headers[TRACE_HEADER] == "trace-async-789"

    main_events = parse_json_logs(caplog, "app.main")
    jobs_events = parse_json_logs(caplog, "app.jobs")

    async_enqueued = next(event for event in main_events if event["event"] == "claim_async_enqueued")
    async_accepted = next(event for event in main_events if event["event"] == "claim_async_accepted")
    eager_dispatch = next(event for event in jobs_events if event["event"] == "claim_job_eager_dispatch")
    job_started = next(event for event in jobs_events if event["event"] == "claim_job_started")
    job_completed = next(event for event in jobs_events if event["event"] == "claim_job_completed")
    webhook_dispatched = next(
        event for event in jobs_events if event["event"] == "claim_webhook_dispatched"
    )

    assert async_enqueued["trace_id"] == "trace-async-789"
    assert async_accepted["trace_id"] == "trace-async-789"
    assert async_enqueued["claim_id"] == claim_id
    assert async_accepted["claim_id"] == claim_id
    assert eager_dispatch["claim_id"] == claim_id
    assert job_started["claim_id"] == claim_id
    assert job_completed["claim_id"] == claim_id
    assert job_completed["signal_count"] == 5
    assert webhook_dispatched["claim_id"] == claim_id
    assert webhook_calls[0][0] == "https://example.com/webhook"

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    reset_job_state()
