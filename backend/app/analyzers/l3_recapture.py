from ..config import get_settings
from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer


class RecaptureAnalyzer(Analyzer):
    """L3 — screenshot / photo-of-screen / print-recapture detection.

    This layer is the counter to screenshot evasion: a recaptured "damage photo" is
    itself a fraud signal (legitimate claims are direct phone captures).

    Phase 0: Sightengine recapture API when keys are configured.
    Phase 2: replace with our own moire/screen-artifact CNN.

    STUB when no API keys: neutral signal.
    """

    layer = Layer.L3_RECAPTURE

    async def _run(self, image: bytes, context: ClaimContext) -> SignalResult:
        settings = get_settings()
        if not settings.sightengine_api_user:
            return SignalResult(
                layer=self.layer,
                score=0.5,
                confidence=0.1,
                evidence={"note": "stub — Sightengine keys not configured"},
            )
        # TODO(phase-0): call Sightengine image-recapture endpoint via httpx,
        # map {screen, print, recapture} probabilities into score/evidence.
        return SignalResult(
            layer=self.layer,
            score=0.5,
            confidence=0.1,
            evidence={"note": "Sightengine call not implemented yet"},
        )
