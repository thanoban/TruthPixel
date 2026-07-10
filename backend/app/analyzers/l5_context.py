import asyncio

import httpx

from ..artifacts import get_artifact_store
from ..config import get_settings
from ..context_checks import combined_similarity, fingerprint_bytes
from ..embeddings import EmbeddingUnavailable, cosine_similarity_01, embed_image_bytes
from ..storage import get_recent_original_artifact_records
from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer

LISTING_MATCH_THRESHOLD = 0.82
LISTING_MISMATCH_THRESHOLD = 0.62
REUSE_MATCH_THRESHOLD = 0.93


def _embed(image_bytes: bytes, settings) -> list[float] | None:
    """Best-effort embedding — returns None (never raises) so callers degrade to v0."""
    if not settings.l5_embedding_enabled:
        return None
    try:
        return embed_image_bytes(
            image_bytes,
            model_name=settings.l5_embedding_model,
            pretrained=settings.l5_embedding_pretrained,
            device=settings.l5_embedding_device,
        )
    except EmbeddingUnavailable:
        return None


async def _blended_similarity(
    claim_fp, claim_embedding: list[float] | None, other_bytes: bytes, settings
) -> tuple[float, str]:
    """v0 hash+histogram, optionally blended with v1 CLIP-embedding cosine similarity.

    Returns (similarity, method) — method is surfaced in evidence so a reviewer/dev can
    see whether the embedding upgrade actually contributed to a given comparison.

    The embedding call runs via asyncio.to_thread — it's a blocking, potentially slow
    (first-use: a real model-weight download; every use after: CPU-bound torch/PIL work)
    synchronous call, and running it directly inside this coroutine would block the whole
    event loop for every concurrent request, not just this one. Found live: an earlier cut
    of this code called it directly and a hung network download stalled the entire server,
    not just the one claim being processed — see docs/CORRECTIONS.md.
    """
    other_fp = fingerprint_bytes(other_bytes)
    hash_hist_score = combined_similarity(claim_fp, other_fp)
    if claim_embedding is None:
        return round(hash_hist_score, 4), "hash+histogram-only"

    other_embedding = await asyncio.to_thread(_embed, other_bytes, settings)
    if other_embedding is None:
        return round(hash_hist_score, 4), "hash+histogram-only"

    embedding_score = cosine_similarity_01(claim_embedding, other_embedding)
    weight = settings.l5_embedding_weight
    blended = (1 - weight) * hash_hist_score + weight * embedding_score
    return round(max(0.0, min(1.0, blended)), 4), "hash+embedding"


class ContextAnalyzer(Analyzer):
    """L5 — e-commerce context cross-check (the moat layer).

    v0 (always available): perceptual-hash + color-histogram similarity.
    v1 (this module): blends in a frozen-CLIP embedding cosine similarity — no training,
      pure inference (`app/embeddings.py`) — for semantic robustness that a pixel-level
      hash misses (crop, angle, lighting changes on the same product).

    Still target, not yet built: Qdrant ANN search (matters once claim volume makes the
    current linear scan over `l5_recent_claim_window` too slow), and external reverse-image
    search (TinEye/SerpAPI) for photos stolen from *outside* our own claims DB.

    The intra-system reuse scan (below) runs on every claim regardless of whether listing
    URLs are supplied — it only needs the claim image and recent claim history, neither of
    which depends on the listing comparison. It used to be gated behind
    `listing_image_urls` being non-empty (a bug: found via scripts/demo.py actually
    exercising the "reused photo, no listing URLs" case live and getting a neutral stub
    back instead of a flag — see docs/CORRECTIONS.md). Listing comparison itself is still
    skipped when no URLs are given; that part genuinely needs them.
    """

    layer = Layer.L5_CONTEXT

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        settings = get_settings()
        claim_fp = fingerprint_bytes(image)
        claim_embedding = await asyncio.to_thread(_embed, image, settings)

        listing_scores: list[dict] = []
        fetch_failures: list[dict] = []
        if context.listing_image_urls:
            urls = context.listing_image_urls[: settings.listing_max_images]
            async with httpx.AsyncClient(timeout=settings.listing_fetch_timeout_seconds) as client:
                for url in urls:
                    try:
                        response = await client.get(url, follow_redirects=True)
                        response.raise_for_status()
                        listing_bytes = response.content
                    except Exception as exc:  # noqa: BLE001
                        fetch_failures.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
                        continue

                    similarity, method = await _blended_similarity(
                        claim_fp, claim_embedding, listing_bytes, settings
                    )
                    listing_scores.append({"url": url, "similarity": similarity, "method": method})

        # Always runs — independent of listing_image_urls, see class docstring.
        reuse_matches: list[dict] = []
        for artifact in get_recent_original_artifact_records(
            exclude_claim_id=claim_id,
            limit=settings.l5_recent_claim_window,
        ):
            try:
                prior_bytes = get_artifact_store().get_bytes(artifact.storage_key)
            except Exception:  # noqa: BLE001
                continue
            similarity, method = await _blended_similarity(claim_fp, claim_embedding, prior_bytes, settings)
            if similarity >= REUSE_MATCH_THRESHOLD:
                reuse_matches.append(
                    {
                        "claim_id": artifact.claim_id,
                        "artifact_id": artifact.id,
                        "similarity": similarity,
                        "method": method,
                    }
                )

        best_listing = max((entry["similarity"] for entry in listing_scores), default=None)
        successful_fetches = len(listing_scores)
        failed_fetches = len(fetch_failures)
        listing_provided = bool(context.listing_image_urls)

        # Reuse match takes priority regardless of listing status — a photo that closely
        # matches a *different* prior claim is suspicious on its own, whether or not this
        # claim also came with listing URLs to compare against.
        if reuse_matches:
            score = 0.92
            confidence = 0.85
            note = "claim image closely matches a previously stored claim photo"
        elif not listing_provided:
            score = 0.5
            confidence = 0.1
            note = "no listing image URLs supplied — listing cross-check skipped (reuse scan still ran)"
        elif best_listing is None:
            score = 0.5
            confidence = 0.2 if failed_fetches else 0.1
            note = "listing images could not be fetched for comparison"
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
                "embedding_available": claim_embedding is not None,
                "embedding_model": settings.l5_embedding_model if claim_embedding is not None else None,
            },
            model_version=(
                f"listing-sim-v1-hash-embed-{settings.l5_embedding_model}"
                if claim_embedding is not None
                else "listing-sim-v1-hash-only"
            ),
        )
