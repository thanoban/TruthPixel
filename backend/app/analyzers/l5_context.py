import httpx

from ..artifacts import get_artifact_store
from ..config import get_settings
from ..context_checks import combined_similarity, fingerprint_bytes
from ..storage import get_recent_original_artifact_records
from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer

LISTING_MATCH_THRESHOLD = 0.82
LISTING_MISMATCH_THRESHOLD = 0.62
REUSE_MATCH_THRESHOLD = 0.93


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

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        if not context.listing_image_urls:
            return SignalResult(
                layer=self.layer,
                score=0.5,
                confidence=0.1,
                evidence={
                    "note": "no listing image URLs supplied — context cross-check skipped",
                    "listing_images_provided": 0,
                    "product_sku": context.product_sku,
                },
            )

        settings = get_settings()
        claim_fp = fingerprint_bytes(image)
        listing_scores: list[dict] = []
        fetch_failures: list[dict] = []
        urls = context.listing_image_urls[: settings.listing_max_images]

        async with httpx.AsyncClient(timeout=settings.listing_fetch_timeout_seconds) as client:
            for url in urls:
                try:
                    response = await client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    listing_fp = fingerprint_bytes(response.content)
                except Exception as exc:  # noqa: BLE001
                    fetch_failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
                    continue

                similarity = round(combined_similarity(claim_fp, listing_fp), 4)
                listing_scores.append({"url": url, "similarity": similarity})

        reuse_matches: list[dict] = []
        for artifact in get_recent_original_artifact_records(
            exclude_claim_id=claim_id,
            limit=settings.l5_recent_claim_window,
        ):
            try:
                prior_bytes = get_artifact_store().get_bytes(artifact.storage_key)
                prior_fp = fingerprint_bytes(prior_bytes)
            except Exception:  # noqa: BLE001
                continue
            similarity = round(combined_similarity(claim_fp, prior_fp), 4)
            if similarity >= REUSE_MATCH_THRESHOLD:
                reuse_matches.append(
                    {
                        "claim_id": artifact.claim_id,
                        "artifact_id": artifact.id,
                        "similarity": similarity,
                    }
                )

        best_listing = max((entry["similarity"] for entry in listing_scores), default=None)
        successful_fetches = len(listing_scores)
        failed_fetches = len(fetch_failures)

        if best_listing is None:
            score = 0.5
            confidence = 0.2 if failed_fetches else 0.1
            note = "listing images could not be fetched for comparison"
        elif reuse_matches:
            score = 0.92
            confidence = 0.85
            note = "claim image closely matches a previously stored claim photo"
        elif best_listing >= LISTING_MATCH_THRESHOLD:
            score = 0.18
            confidence = 0.75 if successful_fetches > 1 else 0.6
            note = "claim image strongly matches the seller listing photos"
        elif best_listing <= LISTING_MISMATCH_THRESHOLD:
            score = 0.78
            confidence = 0.7 if successful_fetches > 1 else 0.55
            note = "claim image looks weakly related to the seller listing photos"
        else:
            score = 0.48
            confidence = 0.35
            note = "listing comparison is inconclusive"

        return SignalResult(
            layer=self.layer,
            score=score,
            confidence=confidence,
            evidence={
                "note": note,
                "product_sku": context.product_sku,
                "listing_images_provided": len(context.listing_image_urls),
                "listing_images_compared": successful_fetches,
                "listing_fetch_failures": fetch_failures,
                "listing_scores": listing_scores,
                "best_listing_similarity": best_listing,
                "reused_claim_matches": reuse_matches,
            },
            model_version="listing-sim-v1",
        )
