import io
from types import SimpleNamespace

import pytest
from PIL import Image

from app.analyzers.l5_context import ContextAnalyzer
from app.schemas import ClaimContext


def make_jpeg(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
    return buf.getvalue()


def fake_settings():
    return SimpleNamespace(
        listing_fetch_timeout_seconds=5.0,
        listing_max_images=5,
        l5_recent_claim_window=20,
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
async def test_context_analyzer_returns_neutral_without_listing_urls():
    result = await ContextAnalyzer().analyze(make_jpeg((40, 80, 120)), ClaimContext())
    assert result.score == 0.5
    assert result.confidence == 0.1


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
