"""End-to-end smoke test: the full graph runs in stub mode (no models, no Vertex)."""

import io

import pytest
from PIL import Image

from app.fusion import fuse
from app.graph import run_claim
from app.schemas import ClaimContext, Layer, SignalResult


def make_jpeg(size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_graph_runs_end_to_end_in_stub_mode():
    report = await run_claim(make_jpeg(), ClaimContext(order_id="A1", product_sku="SKU-9"))
    assert report.claim_id
    assert len(report.signals) == 5
    assert 0.0 <= report.fusion.risk_score <= 1.0
    assert report.report_text
    layers = {s.layer for s in report.signals}
    assert layers == set(Layer)


@pytest.mark.asyncio
async def test_analyzer_error_isolation():
    # A signal with an error must not break fusion.
    ok = SignalResult(layer=Layer.L1_AIGEN, score=0.8, confidence=0.9)
    bad = SignalResult(layer=Layer.L2_FORENSICS, error="boom")
    result = fuse([ok, bad], [])
    assert 0.0 <= result.risk_score <= 1.0


def test_fusion_with_no_signals_forces_review():
    result = fuse([], [])
    assert result.needs_review is True


def test_screenshot_evasion_combo_raises_risk():
    base = [
        SignalResult(layer=Layer.L1_AIGEN, score=0.5, confidence=0.5),
        SignalResult(layer=Layer.L3_RECAPTURE, score=0.9, confidence=0.8),
        SignalResult(
            layer=Layer.L4_METADATA,
            score=0.5,
            confidence=0.15,
            evidence={"exif_present": False},
        ),
    ]
    combo = fuse(base, [])
    no_recapture = fuse(
        [
            base[0],
            SignalResult(layer=Layer.L3_RECAPTURE, score=0.5, confidence=0.8),
            base[2],
        ],
        [],
    )
    assert combo.risk_score > no_recapture.risk_score
