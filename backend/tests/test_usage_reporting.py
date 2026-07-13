import io
import logging

from fastapi.testclient import TestClient
from PIL import Image

from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.main import app
from app.observability import (
    bind_claim_context,
    clear_context,
    ensure_trace_id,
    log_usage_summary,
    record_external_usage,
)
from app.schemas import ClaimContext
from app.storage import (
    create_processing_claim,
    create_tenant,
    get_claim_usage_summary,
    get_tenant_usage_summary,
    init_db,
    reset_storage_state,
    upsert_claim_usage_summary,
)


def make_jpeg(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (90, 120, 210)).save(buf, format="JPEG")
    return buf.getvalue()


def configure_storage_env(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "truthpixel-usage.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    init_db()


def configure_auth_env(monkeypatch, tmp_path) -> None:
    configure_storage_env(monkeypatch, tmp_path)
    monkeypatch.setenv("API_AUTH_ENABLED", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "admin-secret")
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    init_db()


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


def test_claim_usage_summary_returns_zeroes_for_claims_without_usage(monkeypatch, tmp_path):
    configure_storage_env(monkeypatch, tmp_path)
    # claims.tenant_id is a real FK to tenants.tenant_id (enforced on Postgres always, and
    # on SQLite too now — see repository.py::get_engine's PRAGMA foreign_keys=ON, added
    # after this exact class of bug reached production on Supabase). Seed a real tenant
    # row rather than relying on an arbitrary string that happens to satisfy the type.
    create_tenant(name="Tenant Zero", slug="tenant-zero")
    create_processing_claim(
        "claim-zero-usage",
        ClaimContext(order_id="ORD-ZERO"),
        tenant_id="tenant-zero",
    )

    claim_usage = get_claim_usage_summary("claim-zero-usage", tenant_id="tenant-zero")
    tenant_usage = get_tenant_usage_summary("tenant-zero")

    assert claim_usage is not None
    assert claim_usage.total_external_requests == 0
    assert claim_usage.failed_external_requests == 0
    assert claim_usage.estimated_cost_usd == 0.0
    assert claim_usage.providers == {}
    assert tenant_usage.total_claims == 1
    assert tenant_usage.claims_with_usage == 0
    assert tenant_usage.total_external_requests == 0

    reset_storage_state()
    reset_artifact_store_state()
    get_settings.cache_clear()


def test_usage_reporting_persists_failed_calls_and_sanitizes_labels(monkeypatch, tmp_path):
    configure_storage_env(monkeypatch, tmp_path)
    create_tenant(name="Tenant Failed", slug="tenant-failed")
    create_processing_claim(
        "claim-failed-usage",
        ClaimContext(order_id="ORD-FAIL"),
        tenant_id="tenant-failed",
    )

    clear_context()
    ensure_trace_id("trace-usage-failed")
    bind_claim_context(claim_id="claim-failed-usage", tenant_id="tenant-failed")
    record_external_usage(
        provider="HF Inference $$$",
        operation="L1 Weird Op??",
        model="Bad Model?!",
        failed=True,
        estimated_cost_usd=-1.0,
    )
    log_usage_summary(logging.getLogger("app.tests"), outcome="failed")
    clear_context()

    summary = get_claim_usage_summary("claim-failed-usage", tenant_id="tenant-failed")
    assert summary is not None
    assert summary.outcome == "failed"
    assert summary.total_external_requests == 1
    assert summary.failed_external_requests == 1
    assert summary.estimated_cost_usd == 0.0
    assert "hf_inference" in summary.providers
    assert summary.providers["hf_inference"].operations == {"l1_weird_op": 1}
    assert summary.providers["hf_inference"].models == ["bad_model"]

    reset_storage_state()
    reset_artifact_store_state()
    get_settings.cache_clear()


def test_tenant_usage_summary_aggregates_multiple_claims(monkeypatch, tmp_path):
    configure_storage_env(monkeypatch, tmp_path)
    create_tenant(name="Tenant Agg", slug="tenant-agg")
    create_processing_claim("claim-usage-a", ClaimContext(order_id="ORD-A"), tenant_id="tenant-agg")
    create_processing_claim("claim-usage-b", ClaimContext(order_id="ORD-B"), tenant_id="tenant-agg")
    create_processing_claim("claim-usage-c", ClaimContext(order_id="ORD-C"), tenant_id="tenant-agg")

    upsert_claim_usage_summary(
        claim_id="claim-usage-a",
        tenant_id="tenant-agg",
        outcome="completed",
        summary={
            "total_external_requests": 2,
            "failed_external_requests": 0,
            "total_input_tokens": 120,
            "total_output_tokens": 45,
            "estimated_cost_usd": 0.0012,
            "providers": {
                "vertex_ai": {
                    "requests": 2,
                    "failed_requests": 0,
                    "input_tokens": 120,
                    "output_tokens": 45,
                    "estimated_cost_usd": 0.0012,
                    "operations": {"semantic_inspector": 1, "report_writer": 1},
                    "models": ["gemini-2.5-flash"],
                }
            },
        },
    )
    upsert_claim_usage_summary(
        claim_id="claim-usage-b",
        tenant_id="tenant-agg",
        outcome="failed",
        summary={
            "total_external_requests": 1,
            "failed_external_requests": 1,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "estimated_cost_usd": 0.0025,
            "providers": {
                "sightengine": {
                    "requests": 1,
                    "failed_requests": 1,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": 0.0025,
                    "operations": {"l3_recapture_check": 1},
                    "models": ["screen"],
                }
            },
        },
    )

    summary = get_tenant_usage_summary("tenant-agg")

    assert summary.tenant_id == "tenant-agg"
    assert summary.total_claims == 3
    assert summary.claims_with_usage == 2
    assert summary.claims_with_failed_external_requests == 1
    assert summary.total_external_requests == 3
    assert summary.failed_external_requests == 1
    assert summary.total_input_tokens == 120
    assert summary.total_output_tokens == 45
    assert summary.estimated_cost_usd == 0.0037
    assert summary.providers["vertex_ai"].claim_count == 1
    assert summary.providers["vertex_ai"].operations == {
        "report_writer": 1,
        "semantic_inspector": 1,
    }
    assert summary.providers["sightengine"].failed_requests == 1

    reset_storage_state()
    reset_artifact_store_state()
    get_settings.cache_clear()


def test_usage_reporting_routes_isolate_tenants_and_support_admin(monkeypatch, tmp_path):
    configure_auth_env(monkeypatch, tmp_path)

    with TestClient(app) as client:
        tenant_a, key_a = create_tenant_and_key(client, "Tenant A", "primary")
        tenant_b, key_b = create_tenant_and_key(client, "Tenant B", "primary")

        claim_a = client.post(
            "/v1/claims",
            headers={"X-API-Key": key_a},
            files={"image": ("tenant-a.jpg", make_jpeg(), "image/jpeg")},
            data={"order_id": "ORD-A"},
        ).json()
        claim_b = client.post(
            "/v1/claims",
            headers={"X-API-Key": key_b},
            files={"image": ("tenant-b.jpg", make_jpeg(), "image/jpeg")},
            data={"order_id": "ORD-B"},
        ).json()

        upsert_claim_usage_summary(
            claim_id=claim_a["claim_id"],
            tenant_id=tenant_a["tenant_id"],
            outcome="completed",
            summary={
                "total_external_requests": 1,
                "failed_external_requests": 0,
                "total_input_tokens": 12,
                "total_output_tokens": 8,
                "estimated_cost_usd": 0.0004,
                "providers": {
                    "vertex_ai": {
                        "requests": 1,
                        "failed_requests": 0,
                        "input_tokens": 12,
                        "output_tokens": 8,
                        "estimated_cost_usd": 0.0004,
                        "operations": {"semantic_inspector": 1},
                        "models": ["gemini-2.5-flash"],
                    }
                },
            },
        )
        upsert_claim_usage_summary(
            claim_id=claim_b["claim_id"],
            tenant_id=tenant_b["tenant_id"],
            outcome="failed",
            summary={
                "total_external_requests": 2,
                "failed_external_requests": 1,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "estimated_cost_usd": 0.002,
                "providers": {
                    "hf_inference": {
                        "requests": 2,
                        "failed_requests": 1,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "estimated_cost_usd": 0.002,
                        "operations": {"l1_member_query": 2},
                        "models": ["member-a", "member-b"],
                    }
                },
            },
        )

        tenant_claim_usage = client.get(
            f"/v1/claims/{claim_a['claim_id']}/usage",
            headers={"X-API-Key": key_a},
        )
        assert tenant_claim_usage.status_code == 200
        assert tenant_claim_usage.json()["claim_id"] == claim_a["claim_id"]
        assert tenant_claim_usage.json()["tenant_id"] == tenant_a["tenant_id"]

        foreign_claim_usage = client.get(
            f"/v1/claims/{claim_a['claim_id']}/usage",
            headers={"X-API-Key": key_b},
        )
        assert foreign_claim_usage.status_code == 404

        tenant_summary = client.get("/v1/usage/summary", headers={"X-API-Key": key_a})
        assert tenant_summary.status_code == 200
        assert tenant_summary.json()["tenant_id"] == tenant_a["tenant_id"]
        assert tenant_summary.json()["total_claims"] == 1
        assert tenant_summary.json()["estimated_cost_usd"] == 0.0004

        admin_claim_usage = client.get(
            f"/v1/admin/claims/{claim_b['claim_id']}/usage",
            headers={"X-Admin-Token": "admin-secret"},
        )
        assert admin_claim_usage.status_code == 200
        assert admin_claim_usage.json()["tenant_id"] == tenant_b["tenant_id"]
        assert admin_claim_usage.json()["failed_external_requests"] == 1

        admin_summaries = client.get(
            "/v1/admin/usage/summary",
            headers={"X-Admin-Token": "admin-secret"},
        )
        assert admin_summaries.status_code == 200
        payload = {item["tenant_id"]: item for item in admin_summaries.json()}
        assert payload[tenant_a["tenant_id"]]["estimated_cost_usd"] == 0.0004
        assert payload[tenant_b["tenant_id"]]["estimated_cost_usd"] == 0.002

    reset_storage_state()
    reset_artifact_store_state()
    get_settings.cache_clear()
