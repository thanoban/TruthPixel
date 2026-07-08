from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer


class ContextAnalyzer(Analyzer):
    """L5 — e-commerce context cross-check (the moat layer).

    Target:
      - DINOv2 / OpenCLIP embedding of claim photo vs seller listing photos (Qdrant),
        answering "is this even the same product?"
      - Reverse-image search (TinEye / SerpAPI) for reused / stolen damage photos.
      - Order-context sanity (claim date vs EXIF date, category vs damage type).

    No public dataset exists for this — we build seller-listing <-> claim pairs ourselves.

    STUB: neutral unless listing URLs are provided (then flags that matching is pending).
    """

    layer = Layer.L5_CONTEXT

    async def _run(self, image: bytes, context: ClaimContext) -> SignalResult:
        return SignalResult(
            layer=self.layer,
            score=0.5,
            confidence=0.1,
            evidence={
                "note": "stub — embedding match + reverse-image search not wired in",
                "listing_images_provided": len(context.listing_image_urls),
                "product_sku": context.product_sku,
            },
        )
