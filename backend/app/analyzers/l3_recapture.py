import httpx

from ..config import get_settings
from ..observability import record_external_usage
from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer

SIGHTENGINE_CHECK_URL = "https://api.sightengine.com/1.0/check.json"
SIGHTENGINE_MODEL = "recapture"


def _confidence_from_score(score: float) -> float:
    # Sightengine returns a single calibrated score. Distance from the 0.5 decision
    # boundary is the best lightweight proxy we have for confidence in Phase 0.
    return round(max(0.2, min(1.0, abs(score - 0.5) * 2)), 4)


def _extract_api_error(payload: dict) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        for key in ("message", "type", "code"):
            value = error.get(key)
            if value:
                return str(value)
    if error:
        return str(error)
    return f"unexpected response status: {payload.get('status', 'unknown')}"


class RecaptureAnalyzer(Analyzer):
    """L3 — screenshot / photo-of-screen / print-recapture detection.

    This layer is the counter to screenshot evasion: a recaptured "damage photo" is
    itself a fraud signal (legitimate claims are direct phone captures).

    Phase 0: Sightengine recapture API when keys are configured.
    Phase 2: replace with our own moire/screen-artifact CNN.

    STUB when no API keys: neutral signal.
    """

    layer = Layer.L3_RECAPTURE

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        settings = get_settings()
        if not settings.sightengine_api_user or not settings.sightengine_api_secret:
            return SignalResult(
                layer=self.layer,
                score=0.5,
                confidence=0.1,
                evidence={"note": "stub — Sightengine keys not configured"},
            )

        data = {
            "models": SIGHTENGINE_MODEL,
            "api_user": settings.sightengine_api_user,
            "api_secret": settings.sightengine_api_secret,
        }
        files = {"media": ("claim-upload.jpg", image, "application/octet-stream")}

        try:
            async with httpx.AsyncClient(timeout=settings.sightengine_timeout_seconds) as client:
                response = await client.post(SIGHTENGINE_CHECK_URL, data=data, files=files)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            record_external_usage(
                provider="sightengine",
                operation="l3_recapture_check",
                model=SIGHTENGINE_MODEL,
                failed=True,
            )
            raise RuntimeError(f"Sightengine request failed: {exc}") from exc

        payload = response.json()
        if payload.get("status") != "success":
            record_external_usage(
                provider="sightengine",
                operation="l3_recapture_check",
                model=SIGHTENGINE_MODEL,
                failed=True,
            )
            raise RuntimeError(f"Sightengine API failure: {_extract_api_error(payload)}")

        recapture = payload.get("recapture")
        if not isinstance(recapture, dict) or "score" not in recapture:
            raise RuntimeError("Sightengine response missing recapture.score")

        try:
            score = max(0.0, min(1.0, float(recapture["score"])))
        except (TypeError, ValueError) as exc:
            record_external_usage(
                provider="sightengine",
                operation="l3_recapture_check",
                model=SIGHTENGINE_MODEL,
                failed=True,
            )
            raise RuntimeError("Sightengine returned a non-numeric recapture score") from exc

        record_external_usage(
            provider="sightengine",
            operation="l3_recapture_check",
            model=SIGHTENGINE_MODEL,
            estimated_cost_usd=max(
                0.0,
                float(getattr(settings, "sightengine_request_cost_usd", 0.0)),
            ),
        )

        return SignalResult(
            layer=self.layer,
            score=score,
            confidence=_confidence_from_score(score),
            evidence={
                "provider": "sightengine",
                "request_id": payload.get("request", {}).get("id"),
                "operations": payload.get("request", {}).get("operations"),
                "media_id": payload.get("media", {}).get("id"),
                "media_uri": payload.get("media", {}).get("uri"),
                "recapture_threshold_hint": 0.5,
                "note": (
                    "Scores above 0.5 indicate likely recapture per Sightengine docs; "
                    "tune in fusion/reviewer workflow."
                ),
            },
            model_version="sightengine-recapture-beta",
        )
