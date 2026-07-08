from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer


class AiGenAnalyzer(Analyzer):
    """L1 — AI-generation detection.

    Target: CLIP ViT-L/14 features + trained MLP head (UniversalFakeDetect approach),
    trained with screenshot augmentation so it detects post-recompression artifacts.
    Training pipeline lives in ml/layer1_aigen/. Load checkpoint via L1_MODEL_PATH.

    STUB: returns a neutral low-confidence signal until the trained head is wired in.
    """

    layer = Layer.L1_AIGEN

    async def _run(self, image: bytes, context: ClaimContext) -> SignalResult:
        return SignalResult(
            layer=self.layer,
            score=0.5,
            confidence=0.1,
            evidence={"note": "stub — CLIP-head checkpoint not loaded"},
        )
