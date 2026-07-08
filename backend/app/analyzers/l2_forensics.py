from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer


class ForensicsAnalyzer(Analyzer):
    """L2 — manipulation / edit forensics (inpainting, splicing, copy-move).

    Target: TruFor pretrained inference — integrity score + localization heatmap
    (the demo-friendly region overlay for the reviewer dashboard). CAT-Net / MVSS-Net
    are candidate alternates. Runs on serverless GPU in Phase 1.

    STUB: neutral signal; evidence will carry `heatmap_url` once TruFor is wired in.
    """

    layer = Layer.L2_FORENSICS

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        return SignalResult(
            layer=self.layer,
            score=0.5,
            confidence=0.1,
            evidence={"note": "stub — TruFor not wired in", "heatmap_url": None},
        )
