from __future__ import annotations

import asyncio

from ..config import get_settings
from ..schemas import ClaimContext, Layer, SignalResult
from ..signal_artifacts import INTERNAL_HEATMAP_BYTES_KEY
from ..trufor import run_trufor_inference
from .base import Analyzer


class ForensicsAnalyzer(Analyzer):
    """L2 — manipulation / edit forensics (inpainting, splicing, copy-move).

    Target: TruFor pretrained inference — integrity score + localization heatmap
    (the demo-friendly region overlay for the reviewer dashboard). CAT-Net / MVSS-Net
    are candidate alternates. Runs on serverless GPU in Phase 1.

    When the external TruFor checkout + weights are not configured, this layer
    degrades to the neutral stub signal so the rest of the pipeline can still run.
    """

    layer = Layer.L2_FORENSICS

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        settings = get_settings()
        if not settings.l2_trufor_configured:
            return SignalResult(
                layer=self.layer,
                score=0.5,
                confidence=0.1,
                evidence={
                    "note": "stub — L2 TruFor repo/model not configured",
                    "heatmap_available": False,
                    "heatmap_url": None,
                },
            )

        result = await asyncio.to_thread(run_trufor_inference, image)
        return SignalResult(
            layer=self.layer,
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
