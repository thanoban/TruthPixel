import io

from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.main import app
from app.storage import reset_storage_state


def make_jpeg(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (80, 80, 220)).save(buf, format="JPEG")
    return buf.getvalue()


def test_claim_persistence_and_review_flow(monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-test.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
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
        assert len(created["artifacts"]) == 1
        original_artifact = created["artifacts"][0]
        assert original_artifact["kind"] == "original_upload"

        fetched = client.get(f"/v1/claims/{claim_id}")
        assert fetched.status_code == 200
        assert fetched.json()["claim_id"] == claim_id

        listing = client.get("/v1/claims?limit=10&decided=false")
        assert listing.status_code == 200
        list_payload = listing.json()
        assert len(list_payload) == 1
        assert list_payload[0]["claim_id"] == claim_id
        assert list_payload[0]["signal_count"] == 5
        assert list_payload[0]["artifact_count"] == 1

        artifacts = client.get(f"/v1/claims/{claim_id}/artifacts")
        assert artifacts.status_code == 200
        listed_artifacts = artifacts.json()
        assert len(listed_artifacts) == 1

        original_download = client.get(
            f"/v1/claims/{claim_id}/artifacts/{original_artifact['id']}"
        )
        assert original_download.status_code == 200
        assert original_download.headers["content-type"].startswith("image/jpeg")
        assert original_download.content

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

        heatmap_download = client.get(
            f"/v1/claims/{claim_id}/artifacts/{heatmap_artifact['id']}"
        )
        assert heatmap_download.status_code == 200
        assert heatmap_download.headers["content-type"].startswith("image/png")

        audit = client.get(f"/v1/claims/{claim_id}/audit")
        assert audit.status_code == 200
        events = audit.json()
        assert [event["event_type"] for event in events] == [
            "claim_persisted",
            "artifact_stored",
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
