from types import SimpleNamespace

import httpx
import pytest

from app.analyzers.l3_recapture import RecaptureAnalyzer
from app.schemas import ClaimContext


def fake_settings(api_user: str = "", api_secret: str = "", timeout: float = 15.0):
    return SimpleNamespace(
        sightengine_api_user=api_user,
        sightengine_api_secret=api_secret,
        sightengine_timeout_seconds=timeout,
    )


@pytest.mark.asyncio
async def test_recapture_analyzer_returns_stub_without_keys(monkeypatch):
    monkeypatch.setattr(
        "app.analyzers.l3_recapture.get_settings", lambda: fake_settings(api_user="", api_secret="")
    )

    result = await RecaptureAnalyzer().analyze(b"image-bytes", ClaimContext())

    assert result.error is None
    assert result.score == 0.5
    assert result.evidence["note"] == "stub — Sightengine keys not configured"


@pytest.mark.asyncio
async def test_recapture_analyzer_maps_successful_sightengine_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "success",
                "request": {"id": "req_123", "operations": 1},
                "recapture": {"score": 0.91},
                "media": {"id": "med_456", "uri": "claim-upload.jpg"},
            }

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data, files):
            assert data["models"] == "recapture"
            assert data["api_user"] == "user"
            assert data["api_secret"] == "secret"
            assert files["media"][0] == "claim-upload.jpg"
            assert files["media"][1] == b"image-bytes"
            return FakeResponse()

    monkeypatch.setattr(
        "app.analyzers.l3_recapture.get_settings",
        lambda: fake_settings(api_user="user", api_secret="secret"),
    )
    monkeypatch.setattr("app.analyzers.l3_recapture.httpx.AsyncClient", FakeClient)

    result = await RecaptureAnalyzer().analyze(b"image-bytes", ClaimContext())

    assert result.error is None
    assert result.score == 0.91
    assert result.confidence == 0.82
    assert result.model_version == "sightengine-recapture-beta"
    assert result.evidence["provider"] == "sightengine"
    assert result.evidence["request_id"] == "req_123"
    assert result.evidence["media_id"] == "med_456"


@pytest.mark.asyncio
async def test_recapture_analyzer_isolates_sightengine_api_failure(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "failure", "error": {"message": "bad credentials"}}

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data, files):
            return FakeResponse()

    monkeypatch.setattr(
        "app.analyzers.l3_recapture.get_settings",
        lambda: fake_settings(api_user="user", api_secret="secret"),
    )
    monkeypatch.setattr("app.analyzers.l3_recapture.httpx.AsyncClient", FakeClient)

    result = await RecaptureAnalyzer().analyze(b"image-bytes", ClaimContext())

    assert result.score is None
    assert result.error == "RuntimeError: Sightengine API failure: bad credentials"


@pytest.mark.asyncio
async def test_recapture_analyzer_isolates_transport_errors(monkeypatch):
    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data, files):
            request = httpx.Request("POST", url)
            raise httpx.ConnectError("network down", request=request)

    monkeypatch.setattr(
        "app.analyzers.l3_recapture.get_settings",
        lambda: fake_settings(api_user="user", api_secret="secret"),
    )
    monkeypatch.setattr("app.analyzers.l3_recapture.httpx.AsyncClient", FakeClient)

    result = await RecaptureAnalyzer().analyze(b"image-bytes", ClaimContext())

    assert result.score is None
    assert result.error.startswith("RuntimeError: Sightengine request failed:")
