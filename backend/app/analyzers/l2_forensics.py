from __future__ import annotations

import asyncio

from ..config import get_settings
from ..forensics_classic import run_classic_forensics
from ..schemas import ClaimContext, Layer, SignalResult
from ..signal_artifacts import INTERNAL_HEATMAP_BYTES_KEY
from ..trufor import SUSPICIOUS_PIXEL_THRESHOLD, _render_heatmap_png, run_trufor_inference
from .base import Analyzer


def _stub_note(settings) -> str:
    missing = getattr(settings, "l2_trufor_missing_settings", [])
    if not missing or len(missing) == 2:
        return "stub — L2 TruFor repo/model not configured"
    return f"stub — L2 TruFor missing {', '.join(missing)}"


class ForensicsAnalyzer(Analyzer):
    """L2 — manipulation / edit forensics (inpainting, splicing, copy-move).

    Target: TruFor pretrained inference — integrity score + localization heatmap
    (the demo-friendly region overlay for the reviewer dashboard). CAT-Net / MVSS-Net
    are candidate alternates. Runs on serverless GPU in Phase 1.

    When the external TruFor checkout + weights are not configured, this layer
    falls back to classical CPU-only forensics (ELA + noise inconsistency +
    JPEG ghosting) so L2 still contributes a real signal and heatmap.
    """

    layer = Layer.L2_FORENSICS

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        settings = get_settings()
        if not settings.l2_trufor_configured:
            result = await asyncio.to_thread(run_classic_forensics, image)
            heatmap_png, resized_map, _ = _render_heatmap_png(
                result.anomaly_map,
                confidence_map=None,
                image_size=result.image_size,
            )
            return SignalResult(
                layer=self.layer,
                score=result.score,
                confidence=result.confidence,
                evidence={
                    "provider": "classic-cpu",
                    "fallback_reason": _stub_note(settings),
                    "runtime_status": getattr(settings, "l2_trufor_runtime_status", "stub"),
                    "heatmap_available": False,
                    "heatmap_download_path": None,
                    "heatmap_url": None,
                    "heatmap_mean": round(float(resized_map.mean()), 4),
                    "heatmap_max": round(float(resized_map.max()), 4),
                    "suspicious_pixel_fraction": round(
                        float((resized_map >= SUSPICIOUS_PIXEL_THRESHOLD).mean()), 4
                    ),
                    "ela_inconsistency": result.ela_inconsistency,
                    "noise_inconsistency": result.noise_inconsistency,
                    "ghost_inconsistency": result.ghost_inconsistency,
                    INTERNAL_HEATMAP_BYTES_KEY: heatmap_png,
                },
                model_version="classic-forensics-0.1",
            )

        result = await asyncio.to_thread(run_trufor_inference, image)
        return SignalResult(
            layer=self.layer,
            score=result.score,
            confidence=result.confidence,
            evidence={
                "provider": "trufor",
                "runtime_status": getattr(settings, "l2_trufor_runtime_status", "configured"),
                "heatmap_available": False,
                "heatmap_download_path": None,
                "heatmap_url": None,
                "heatmap_mean": result.heatmap_mean,
                "heatmap_max": result.heatmap_max,
                "confidence_map_mean": result.confidence_mean,
                "suspicious_pixel_fraction": result.suspicious_pixel_fraction,
                INTERNAL_HEATMAP_BYTES_KEY: result.heatmap_png,
            },
            model_version=result.model_version,
        )
