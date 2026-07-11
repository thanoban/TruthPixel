from __future__ import annotations

import asyncio
import logging

from ..config import get_settings
from ..forensics_classic import ClassicForensicsResult, run_classic_forensics
from ..schemas import ClaimContext, Layer, SignalResult
from ..signal_artifacts import INTERNAL_HEATMAP_BYTES_KEY
from ..trufor import TruForResult, render_heatmap_png, run_trufor_inference
from .base import Analyzer

logger = logging.getLogger(__name__)


def _signal_from_trufor(result: TruForResult) -> SignalResult:
    return SignalResult(
        layer=Layer.L2_FORENSICS,
        score=result.score,
        confidence=result.confidence,
        evidence={
            "provider": "trufor",
            "heatmap_available": False,
            "heatmap_url": None,
            "heatmap_mean": result.heatmap_mean,
            "heatmap_max": result.heatmap_max,
            "confidence_map_mean": result.confidence_mean,
            "suspicious_pixel_fraction": result.suspicious_pixel_fraction,
            INTERNAL_HEATMAP_BYTES_KEY: result.heatmap_png,
        },
        model_version=result.model_version,
    )


def _signal_from_classic(result: ClassicForensicsResult, *, fallback_reason: str | None) -> SignalResult:
    heatmap_png, resized_map, _ = render_heatmap_png(result.anomaly_map, None, result.image_size)
    evidence = {
        "provider": "classic_forensics",
        "heatmap_available": False,
        "heatmap_url": None,
        "heatmap_mean": round(float(resized_map.mean()), 4),
        "heatmap_max": round(float(resized_map.max()), 4),
        "suspicious_pixel_fraction": round(float((resized_map >= 0.65).mean()), 4),
        "ela_inconsistency": result.ela_inconsistency,
        "noise_inconsistency": result.noise_inconsistency,
        "ghost_inconsistency": result.ghost_inconsistency,
        INTERNAL_HEATMAP_BYTES_KEY: heatmap_png,
    }
    if fallback_reason is not None:
        evidence["fallback_reason"] = fallback_reason
    return SignalResult(
        layer=Layer.L2_FORENSICS,
        score=result.score,
        confidence=result.confidence,
        evidence=evidence,
        model_version="classic:ela-noise-ghost:v1",
    )


class ForensicsAnalyzer(Analyzer):
    """L2 — manipulation / edit forensics (inpainting, splicing, copy-move).

    Target: TruFor pretrained inference — integrity score + localization heatmap
    (the demo-friendly region overlay for the reviewer dashboard). CAT-Net / MVSS-Net
    are candidate alternates. Runs on serverless GPU in Phase 1.

    TruFor is preferred when configured. Otherwise, or when TruFor fails at runtime,
    this layer falls back to a CPU-only classical detector that still produces a
    real localization heatmap for artifact persistence and reviewer inspection.
    """

    layer = Layer.L2_FORENSICS

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        settings = get_settings()
        if settings.l2_trufor_configured:
            try:
                result = await asyncio.to_thread(run_trufor_inference, image)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "L2 TruFor inference failed; falling back to classical forensics: %s: %s",
                    type(exc).__name__,
                    exc,
                )
            else:
                return _signal_from_trufor(result)

        fallback_reason = (
            "trufor_unconfigured" if not settings.l2_trufor_configured else "trufor_runtime_failure"
        )
        result = await asyncio.to_thread(run_classic_forensics, image)
        return _signal_from_classic(result, fallback_reason=fallback_reason)
