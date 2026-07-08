import io
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.analyzers.l2_forensics import ForensicsAnalyzer
from app.artifacts import reset_artifact_store_state
from app.config import get_settings
from app.schemas import ClaimContext, Layer, SignalResult
from app.signal_artifacts import INTERNAL_HEATMAP_BYTES_KEY, persist_signal_artifacts
from app.storage import (
    create_processing_claim,
    init_db,
    list_claim_artifacts,
    reset_storage_state,
)
from app.trufor import TruForResult


def make_png(size=(24, 24)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, (255, 0, 0, 180)).save(buffer, format="PNG")
    return buffer.getvalue()


def configured_settings(enabled: bool):
    return SimpleNamespace(l2_trufor_configured=enabled)


@pytest.mark.asyncio
async def test_forensics_analyzer_returns_stub_without_trufor(monkeypatch):
    monkeypatch.setattr(
        "app.analyzers.l2_forensics.get_settings", lambda: configured_settings(enabled=False)
    )

    result = await ForensicsAnalyzer().analyze(b"image-bytes", ClaimContext())

    assert result.error is None
    assert result.layer == Layer.L2_FORENSICS
    assert result.score == 0.5
    assert result.evidence["note"] == "stub — L2 TruFor repo/model not configured"
    assert result.evidence["heatmap_url"] is None


@pytest.mark.asyncio
async def test_forensics_analyzer_maps_trufor_output(monkeypatch):
    monkeypatch.setattr(
        "app.analyzers.l2_forensics.get_settings", lambda: configured_settings(enabled=True)
    )
    monkeypatch.setattr(
        "app.analyzers.l2_forensics.run_trufor_inference",
        lambda image: TruForResult(
            score=0.88,
            confidence=0.73,
            anomaly_map=np.array([[0.1, 0.9], [0.2, 0.7]], dtype=np.float32),
            confidence_map=np.array([[0.8, 0.9], [0.7, 0.6]], dtype=np.float32),
            heatmap_png=make_png(),
            heatmap_mean=0.42,
            heatmap_max=0.91,
            confidence_mean=0.75,
            suspicious_pixel_fraction=0.25,
            model_version="trufor:test-weights.pth.tar",
        ),
    )

    result = await ForensicsAnalyzer().analyze(b"image-bytes", ClaimContext())

    assert result.error is None
    assert result.score == 0.88
    assert result.confidence == 0.73
    assert result.model_version == "trufor:test-weights.pth.tar"
    assert result.evidence["provider"] == "trufor"
    assert result.evidence["heatmap_url"] is None
    assert result.evidence["heatmap_available"] is False
    assert result.evidence["suspicious_pixel_fraction"] == 0.25
    assert INTERNAL_HEATMAP_BYTES_KEY in result.evidence


def test_persist_signal_artifacts_saves_heatmap(monkeypatch, tmp_path):
    db_path = tmp_path / "truthpixel-forensics.db"
    artifact_dir = tmp_path / "artifacts"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_ARTIFACT_DIR", artifact_dir.as_posix())
    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
    init_db()

    create_processing_claim("claim-forensics", ClaimContext(order_id="ORD-1"), tenant_id="local-dev")
    signal = SignalResult(
        layer=Layer.L2_FORENSICS,
        score=0.81,
        confidence=0.7,
        evidence={
            "provider": "trufor",
            "heatmap_available": False,
            "heatmap_url": None,
            INTERNAL_HEATMAP_BYTES_KEY: make_png(),
        },
    )

    persist_signal_artifacts("claim-forensics", [signal], tenant_id="local-dev")

    artifacts = list_claim_artifacts("claim-forensics", tenant_id="local-dev")
    assert artifacts is not None
    assert len(artifacts) == 1
    assert artifacts[0].kind == "heatmap"
    assert signal.evidence["heatmap_available"] is True
    assert signal.evidence["heatmap_artifact_id"] == artifacts[0].id
    assert signal.evidence["heatmap_url"] == artifacts[0].download_path
    assert INTERNAL_HEATMAP_BYTES_KEY not in signal.evidence

    get_settings.cache_clear()
    reset_storage_state()
    reset_artifact_store_state()
