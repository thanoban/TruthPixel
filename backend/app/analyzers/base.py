from abc import ABC, abstractmethod

from ..schemas import ClaimContext, Layer, SignalResult


class Analyzer(ABC):
    """One deterministic signal layer. Real models plug in behind this interface.

    Contract: analyze() must never raise — return SignalResult(error=...) instead,
    so one failing layer never kills the pipeline (fusion handles missing signals).
    """

    layer: Layer

    @abstractmethod
    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult: ...

    async def analyze(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        try:
            return await self._run(image, context, claim_id)
        except Exception as exc:  # noqa: BLE001 — error isolation is the point
            return SignalResult(layer=self.layer, error=f"{type(exc).__name__}: {exc}")
