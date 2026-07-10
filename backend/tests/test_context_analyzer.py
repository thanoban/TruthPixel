import io
from types import SimpleNamespace

import pytest
from PIL import Image

from app.analyzers.l5_context import ContextAnalyzer
from app.embeddings import EmbeddingUnavailable
from app.schemas import ClaimContext


def make_jpeg(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
    return buf.getvalue()


def fake_settings(embedding_enabled: bool = False, embedding_weight: float = 0.5):
    return SimpleNamespace(
        listing_fetch_timeout_seconds=5.0,
        listing_max_images=5,
        l5_recent_claim_window=20,
        l5_embedding_enabled=embedding_enabled,
        l5_embedding_model="ViT-B-32",
        l5_embedding_pretrained="openai",
        l5_embedding_device="cpu",
        l5_embedding_weight=embedding_weight,
    )


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, responses: dict[str, bytes], timeout: float):
        self.responses = responses
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, follow_redirects: bool = True):
        if url not in self.responses:
            raise RuntimeError("missing url")
        return FakeResponse(self.responses[url])


@pytest.mark.asyncio
async def test_context_analyzer_returns_neutral_without_listing_urls(monkeypatch):
    monkeypatch.setattr("app.analyzers.l5_context.get_settings", fake_settings)
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_recent_original_artifact_records", lambda **kwargs: []
    )

    result = await ContextAnalyzer().analyze(make_jpeg((40, 80, 120)), ClaimContext())
    assert result.score == 0.5
    assert result.confidence == 0.1
    assert "reuse scan still ran" in result.evidence["note"]


@pytest.mark.asyncio
async def test_context_analyzer_detects_strong_listing_match(monkeypatch):
    listing = make_jpeg((20, 40, 60))
    monkeypatch.setattr("app.analyzers.l5_context.get_settings", fake_settings)
    monkeypatch.setattr(
        "app.analyzers.l5_context.httpx.AsyncClient",
        lambda timeout: FakeClient({"https://listing/a.jpg": listing}, timeout),
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_recent_original_artifact_records", lambda **kwargs: []
    )

    result = await ContextAnalyzer().analyze(
        listing,
        ClaimContext(order_id="ORD-1", listing_image_urls=["https://listing/a.jpg"]),
    )

    assert result.score is not None and result.score < 0.3
    assert result.confidence >= 0.6
    assert result.evidence["best_listing_similarity"] >= 0.82


@pytest.mark.asyncio
async def test_context_analyzer_detects_listing_mismatch(monkeypatch):
    claim = make_jpeg((240, 10, 10))
    listing = make_jpeg((10, 220, 10))
    monkeypatch.setattr("app.analyzers.l5_context.get_settings", fake_settings)
    monkeypatch.setattr(
        "app.analyzers.l5_context.httpx.AsyncClient",
        lambda timeout: FakeClient({"https://listing/b.jpg": listing}, timeout),
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_recent_original_artifact_records", lambda **kwargs: []
    )

    result = await ContextAnalyzer().analyze(
        claim,
        ClaimContext(order_id="ORD-2", listing_image_urls=["https://listing/b.jpg"]),
    )

    assert result.score is not None and result.score > 0.6
    assert result.evidence["best_listing_similarity"] <= 0.62


@pytest.mark.asyncio
async def test_context_analyzer_flags_reused_claim_photo(monkeypatch):
    claim = make_jpeg((90, 90, 90))
    monkeypatch.setattr("app.analyzers.l5_context.get_settings", fake_settings)
    monkeypatch.setattr(
        "app.analyzers.l5_context.httpx.AsyncClient",
        lambda timeout: FakeClient({"https://listing/c.jpg": make_jpeg((30, 30, 240))}, timeout),
    )

    prior_artifact = SimpleNamespace(claim_id="older-claim", id=7, storage_key="claims/older/original.jpg")
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_recent_original_artifact_records",
        lambda **kwargs: [prior_artifact],
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_artifact_store",
        lambda: SimpleNamespace(get_bytes=lambda storage_key: claim),
    )

    result = await ContextAnalyzer().analyze(
        claim,
        ClaimContext(order_id="ORD-3", listing_image_urls=["https://listing/c.jpg"]),
    )

    assert result.score is not None and result.score >= 0.9
    assert result.evidence["reused_claim_matches"][0]["claim_id"] == "older-claim"


@pytest.mark.asyncio
async def test_context_analyzer_flags_reused_photo_even_without_listing_urls(monkeypatch):
    """Regression test for a real bug found via scripts/demo.py: the reuse scan doesn't
    need listing URLs at all (it only compares against recent claim history), but used to
    be gated behind listing_image_urls being non-empty — so a claim submitted with no
    listing photos got a neutral stub even when it was an exact reuse of a prior claim's
    photo. See docs/CORRECTIONS.md.
    """
    claim = make_jpeg((77, 77, 77))
    monkeypatch.setattr("app.analyzers.l5_context.get_settings", fake_settings)

    prior_artifact = SimpleNamespace(claim_id="older-claim-2", id=9, storage_key="claims/older2/original.jpg")
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_recent_original_artifact_records",
        lambda **kwargs: [prior_artifact],
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_artifact_store",
        lambda: SimpleNamespace(get_bytes=lambda storage_key: claim),
    )

    # No listing_image_urls at all — this is the exact scenario the bug missed.
    result = await ContextAnalyzer().analyze(claim, ClaimContext(order_id="ORD-NO-LISTING"))

    assert result.score is not None and result.score >= 0.9
    assert result.evidence["reused_claim_matches"][0]["claim_id"] == "older-claim-2"
    assert result.evidence["listing_images_provided"] == 0


@pytest.mark.asyncio
async def test_context_analyzer_blends_embedding_similarity_when_available(monkeypatch):
    """L5 v1: embedding similarity should visibly move the score, not just be decorative."""
    claim = make_jpeg((90, 90, 90))
    listing = make_jpeg((91, 91, 91))  # near-identical hash/histogram baseline

    monkeypatch.setattr(
        "app.analyzers.l5_context.get_settings",
        lambda: fake_settings(embedding_enabled=True, embedding_weight=1.0),
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.httpx.AsyncClient",
        lambda timeout: FakeClient({"https://listing/d.jpg": listing}, timeout),
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_recent_original_artifact_records", lambda **kwargs: []
    )

    # weight=1.0 means the blended score is *entirely* the embedding term — deterministic
    # fake vectors let us assert the exact resulting similarity without running real CLIP.
    vectors = {claim: [1.0, 0.0], listing: [0.0, 1.0]}  # orthogonal -> cosine 0 -> scaled 0.5
    monkeypatch.setattr(
        "app.analyzers.l5_context.embed_image_bytes",
        lambda image_bytes, **kwargs: vectors[image_bytes],
    )

    result = await ContextAnalyzer().analyze(
        claim,
        ClaimContext(order_id="ORD-4", listing_image_urls=["https://listing/d.jpg"]),
    )

    assert result.evidence["listing_scores"][0]["similarity"] == pytest.approx(0.5)
    assert result.evidence["listing_scores"][0]["method"] == "hash+embedding"
    assert result.evidence["embedding_available"] is True
    assert result.evidence["embedding_model"] == "ViT-B-32"
    assert result.model_version == "listing-sim-v1-hash-embed-ViT-B-32"


@pytest.mark.asyncio
async def test_context_analyzer_falls_back_when_embedding_unavailable(monkeypatch):
    """Embedding path failing (no torch, model load error, ...) must never break L5."""
    claim = make_jpeg((20, 40, 60))
    listing = make_jpeg((20, 40, 60))

    monkeypatch.setattr(
        "app.analyzers.l5_context.get_settings",
        lambda: fake_settings(embedding_enabled=True),
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.httpx.AsyncClient",
        lambda timeout: FakeClient({"https://listing/e.jpg": listing}, timeout),
    )
    monkeypatch.setattr(
        "app.analyzers.l5_context.get_recent_original_artifact_records", lambda **kwargs: []
    )

    def _raise(*args, **kwargs):
        raise EmbeddingUnavailable("PyTorch is required for L5 embeddings.")

    monkeypatch.setattr("app.analyzers.l5_context.embed_image_bytes", _raise)

    result = await ContextAnalyzer().analyze(
        claim,
        ClaimContext(order_id="ORD-5", listing_image_urls=["https://listing/e.jpg"]),
    )

    assert result.error is None
    assert result.evidence["listing_scores"][0]["method"] == "hash+histogram-only"
    assert result.evidence["embedding_available"] is False
    assert result.model_version == "listing-sim-v1-hash-only"
