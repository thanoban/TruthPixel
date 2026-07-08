import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.main import app
from app.storage import reset_storage_state
from app.trufor import TruForResult


def make_jpeg(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (80, 80, 220)).save(buf, format="JPEG")
    return buf.getvalue()


def make_png(size=(32, 32), color=(255, 80, 0, 180)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_claim_persistence_and_review_flow(monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-test.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    monkeypatch.setenv("L2_TRUFOR_REPO_DIR", "D:/fake/trufor")
    monkeypatch.setenv("L2_TRUFOR_MODEL_FILE", "D:/fake/trufor/model.pth.tar")
    monkeypatch.setattr(
        "app.analyzers.l2_forensics.run_trufor_inference",
        lambda image: TruForResult(
            score=0.84,
            confidence=0.69,
            anomaly_map=np.array([[0.1, 0.9], [0.2, 0.8]], dtype=np.float32),
            confidence_map=np.array([[0.8, 0.7], [0.6, 0.9]], dtype=np.float32),
            heatmap_png=make_png(),
            heatmap_mean=0.45,
            heatmap_max=0.93,
            confidence_mean=0.75,
            suspicious_pixel_fraction=0.31,
            model_version="trufor:test-weights.pth.tar",
        ),
    )
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()

    with TestClient(app) as client:
        response = client.post(
            "/v1/claims",
            files={"image": ("sample.jpg", make_jpeg(), "image/jpeg")},
            data={"order_id": "ORD-1", "product_sku": "SKU-1", "claim_reason": "damage"},
        )
        assert response.status_code == 200
        created = response.json()
        claim_id = created["claim_id"]
        assert created["context"]["order_id"] == "ORD-1"
        assert "created_at" in created
        assert created["decision"] is None
        assert len(created["artifacts"]) == 2
        original_artifact = created["artifacts"][0]
        assert original_artifact["kind"] == "original_upload"
        heatmap_artifact = created["artifacts"][1]
        assert heatmap_artifact["kind"] == "heatmap"

        l2_signal = next(signal for signal in created["signals"] if signal["layer"] == "l2_forensics")
        assert l2_signal["evidence"]["provider"] == "trufor"
        assert l2_signal["evidence"]["heatmap_available"] is True
        assert l2_signal["evidence"]["heatmap_url"] == heatmap_artifact["download_path"]

        fetched = client.get(f"/v1/claims/{claim_id}")
        assert fetched.status_code == 200
        assert fetched.json()["claim_id"] == claim_id

        listing = client.get("/v1/claims?limit=10&decided=false")
        assert listing.status_code == 200
        list_payload = listing.json()
        assert len(list_payload) == 1
        assert list_payload[0]["claim_id"] == claim_id
        assert list_payload[0]["signal_count"] == 5
        assert list_payload[0]["artifact_count"] == 2

        artifacts = client.get(f"/v1/claims/{claim_id}/artifacts")
        assert artifacts.status_code == 200
        listed_artifacts = artifacts.json()
        assert len(listed_artifacts) == 2

        original_download = client.get(
            f"/v1/claims/{claim_id}/artifacts/{original_artifact['id']}"
        )
        assert original_download.status_code == 200
        assert original_download.headers["content-type"].startswith("image/jpeg")
        assert original_download.content

        heatmap_download = client.get(f"/v1/claims/{claim_id}/artifacts/{heatmap_artifact['id']}")
        assert heatmap_download.status_code == 200
        assert heatmap_download.headers["content-type"].startswith("image/png")
        assert heatmap_download.content

        decision = client.post(
            f"/v1/claims/{claim_id}/decision",
            json={
                "reviewer_id": "reviewer-7",
                "decision": "reject",
                "reason": "recapture and metadata look suspicious",
            },
        )
        assert decision.status_code == 200
        decided = decision.json()
        assert decided["decision"]["reviewer_id"] == "reviewer-7"
        assert decided["decision"]["decision"] == "reject"

        decided_listing = client.get("/v1/claims?decided=true")
        assert decided_listing.status_code == 200
        assert decided_listing.json()[0]["decision"]["decision"] == "reject"

        heatmap_bytes = io.BytesIO()
        Image.new("RGB", (32, 32), (255, 0, 0)).save(heatmap_bytes, format="PNG")
        heatmap_upload = client.post(
            f"/v1/claims/{claim_id}/artifacts/heatmap",
            files={"heatmap": ("heatmap.png", heatmap_bytes.getvalue(), "image/png")},
        )
        assert heatmap_upload.status_code == 200
        heatmap_artifact = heatmap_upload.json()
        assert heatmap_artifact["kind"] == "heatmap"

        uploaded_heatmap_download = client.get(
            f"/v1/claims/{claim_id}/artifacts/{heatmap_artifact['id']}"
        )
        assert uploaded_heatmap_download.status_code == 200
        assert uploaded_heatmap_download.headers["content-type"].startswith("image/png")

        audit = client.get(f"/v1/claims/{claim_id}/audit")
        assert audit.status_code == 200
        events = audit.json()
        assert [event["event_type"] for event in events] == [
            "artifact_stored",
            "artifact_stored",
            "claim_persisted",
            "decision_recorded",
            "artifact_stored",
        ]

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def test_missing_claim_returns_404(monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-test.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()

    with TestClient(app) as client:
        response = client.get("/v1/claims/missing-claim")
        assert response.status_code == 404

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
