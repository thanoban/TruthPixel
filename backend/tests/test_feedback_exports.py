import csv
import io

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.main import app
from app.storage import reset_storage_state
from app.trufor import TruForResult


def make_jpeg(size=(64, 64), color=(80, 80, 220)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def make_png(size=(32, 32), color=(255, 80, 0, 180)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


def configure_env(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "truthpixel-feedback.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-secret")
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


def create_claim_and_decide(
    client: TestClient,
    *,
    api_key: str,
    order_id: str,
    decision: str,
    reviewer_id: str,
    reason: str,
) -> str:
    create_response = client.post(
        "/v1/claims",
        headers={"X-API-Key": api_key},
        files={"image": ("sample.jpg", make_jpeg(), "image/jpeg")},
        data={"order_id": order_id, "product_sku": f"SKU-{order_id}", "claim_reason": "damage"},
    )
    assert create_response.status_code == 200
    claim_id = create_response.json()["claim_id"]

    decision_response = client.post(
        f"/v1/claims/{claim_id}/decision",
        headers={"X-API-Key": api_key},
        json={"reviewer_id": reviewer_id, "decision": decision, "reason": reason},
    )
    assert decision_response.status_code == 200
    return claim_id


def test_tenant_label_export_is_scoped(monkeypatch, tmp_path):
    configure_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        tenant_a, key_a = create_tenant_and_key(client, "Tenant A", "primary")
        tenant_b, key_b = create_tenant_and_key(client, "Tenant B", "primary")

        claim_a_reject = create_claim_and_decide(
            client,
            api_key=key_a,
            order_id="ORD-A-REJECT",
            decision="reject",
            reviewer_id="reviewer-a",
            reason="fraud indicators present",
        )
        create_claim_and_decide(
            client,
            api_key=key_a,
            order_id="ORD-A-MORE-INFO",
            decision="needs_more_info",
            reviewer_id="reviewer-a",
            reason="need more photos",
        )
        create_claim_and_decide(
            client,
            api_key=key_b,
            order_id="ORD-B-APPROVE",
            decision="approve",
            reviewer_id="reviewer-b",
            reason="looks authentic",
        )

        tenant_export = client.get(
            "/v1/labels/export?training_ready_only=true",
            headers={"X-API-Key": key_a},
        )
        assert tenant_export.status_code == 200
        exported = tenant_export.json()
        assert len(exported) == 1
        assert exported[0]["claim_id"] == claim_a_reject
        assert exported[0]["tenant_id"] == tenant_a["tenant_id"]
        assert exported[0]["fraud_label"] == 1
        assert exported[0]["review_decision"] == "reject"
        assert exported[0]["original_artifact_download_path"].startswith(
            f"/v1/claims/{claim_a_reject}/artifacts/"
        )

        tenant_summary = client.get("/v1/labels/summary", headers={"X-API-Key": key_a})
        assert tenant_summary.status_code == 200
        summary = tenant_summary.json()
        assert summary["total_labeled_claims"] == 2
        assert summary["training_ready_claims"] == 1
        assert summary["counts_by_tenant"] == [{"tenant_id": tenant_a["tenant_id"], "count": 2}]

        foreign_export = client.get("/v1/labels/export", headers={"X-API-Key": key_b})
        assert foreign_export.status_code == 200
        assert len(foreign_export.json()) == 1
        assert foreign_export.json()[0]["tenant_id"] == tenant_b["tenant_id"]

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()


def test_admin_label_export_summary_and_csv(monkeypatch, tmp_path):
    configure_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        tenant_a, key_a = create_tenant_and_key(client, "Tenant A", "primary")
        tenant_b, key_b = create_tenant_and_key(client, "Tenant B", "primary")

        claim_a = create_claim_and_decide(
            client,
            api_key=key_a,
            order_id="ORD-A-REJECT",
            decision="reject",
            reviewer_id="reviewer-a",
            reason="fraud indicators present",
        )
        create_claim_and_decide(
            client,
            api_key=key_a,
            order_id="ORD-A-MORE-INFO",
            decision="needs_more_info",
            reviewer_id="reviewer-a",
            reason="need more photos",
        )
        claim_b = create_claim_and_decide(
            client,
            api_key=key_b,
            order_id="ORD-B-APPROVE",
            decision="approve",
            reviewer_id="reviewer-b",
            reason="looks authentic",
        )

        summary_response = client.get(
            "/v1/admin/labels/summary",
            headers={"X-Admin-Token": "admin-secret"},
        )
        assert summary_response.status_code == 200
        summary = summary_response.json()
        assert summary["total_labeled_claims"] == 3
        assert summary["training_ready_claims"] == 2
        assert {item["decision"]: item["count"] for item in summary["counts_by_decision"]} == {
            "approve": 1,
            "reject": 1,
            "needs_more_info": 1,
        }

        export_response = client.get(
            f"/v1/admin/labels/export?tenant_id={tenant_a['tenant_id']}",
            headers={"X-Admin-Token": "admin-secret"},
        )
        assert export_response.status_code == 200
        exported = export_response.json()
        assert len(exported) == 2
        assert all(item["tenant_id"] == tenant_a["tenant_id"] for item in exported)

        csv_response = client.get(
            "/v1/admin/labels/export.csv?training_ready_only=true",
            headers={"X-Admin-Token": "admin-secret"},
        )
        assert csv_response.status_code == 200
        assert csv_response.headers["content-type"].startswith("text/csv")
        rows = list(csv.DictReader(io.StringIO(csv_response.text)))
        assert len(rows) == 2
        exported_claim_ids = {row["claim_id"] for row in rows}
        assert exported_claim_ids == {claim_a, claim_b}
        assert {row["fraud_label"] for row in rows} == {"0", "1"}

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
