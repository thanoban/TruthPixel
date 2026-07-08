from types import SimpleNamespace

import httpx
import pytest

from app.analyzers.l1_aigen import AiGenAnalyzer
from app.hf_inference import ai_probability_from_predictions
from app.schemas import ClaimContext


def fake_settings(token: str = "", models: list[str] | None = None):
    models = models or []
    return SimpleNamespace(
        l1_model_path="",
        l1_model_device="auto",
        hf_api_token=token,
        l1_hf_model_list=models,
        l1_hf_ensemble_configured=bool(token and models),
        hf_inference_timeout_seconds=30.0,
    )


# --- label mapping: the part that makes heterogeneous models interchangeable ---

def test_label_mapping_handles_both_class_names():
    assert ai_probability_from_predictions(
        [{"label": "artificial", "score": 0.9}, {"label": "human", "score": 0.1}]
    ) == pytest.approx(0.9)
    # different vocabulary, same meaning
    assert ai_probability_from_predictions(
        [{"label": "AI", "score": 0.2}, {"label": "Real", "score": 0.8}]
    ) == pytest.approx(0.2)


def test_label_mapping_returns_none_for_unknown_vocabulary():
    assert ai_probability_from_predictions([{"label": "cat", "score": 0.9}]) is None


# --- analyzer behaviour ---

@pytest.mark.asyncio
async def test_l1_returns_stub_when_nothing_configured(monkeypatch):
    monkeypatch.setattr("app.analyzers.l1_aigen.get_settings", lambda: fake_settings())
    result = await AiGenAnalyzer().analyze(b"img", ClaimContext())
    assert result.error is None
    assert result.score == 0.5
    assert "stub" in result.evidence["note"]


@pytest.mark.asyncio
async def test_l1_hf_ensemble_averages_members(monkeypatch):
    responses = {
        "modelA": [{"label": "artificial", "score": 0.8}, {"label": "human", "score": 0.2}],
        "modelB": [{"label": "ai", "score": 0.6}, {"label": "real", "score": 0.4}],
    }

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content, headers):
            assert headers["Authorization"] == "Bearer tok"
            model = url.rsplit("/", 1)[-1]
            return FakeResponse(responses[model])

    monkeypatch.setattr(
        "app.analyzers.l1_aigen.get_settings",
        lambda: fake_settings(token="tok", models=["modelA", "modelB"]),
    )
    monkeypatch.setattr("app.hf_inference.httpx.AsyncClient", FakeClient)

    result = await AiGenAnalyzer().analyze(b"img", ClaimContext())
    assert result.error is None
    assert result.score == pytest.approx(0.7)  # mean(0.8, 0.6)
    assert result.evidence["provider"] == "hf-inference-ensemble"
    assert result.evidence["members_responded"] == 2


@pytest.mark.asyncio
async def test_l1_hf_ensemble_tolerates_one_member_failing(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"label": "artificial", "score": 0.9}, {"label": "human", "score": 0.1}]

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content, headers):
            if url.endswith("modelDown"):
                raise httpx.ConnectError("down", request=httpx.Request("POST", url))
            return FakeResponse()

    monkeypatch.setattr(
        "app.analyzers.l1_aigen.get_settings",
        lambda: fake_settings(token="tok", models=["modelUp", "modelDown"]),
    )
    monkeypatch.setattr("app.hf_inference.httpx.AsyncClient", FakeClient)

    result = await AiGenAnalyzer().analyze(b"img", ClaimContext())
    assert result.error is None
    assert result.score == pytest.approx(0.9)  # only the surviving member
    assert result.evidence["members_responded"] == 1
    assert result.evidence["members_total"] == 2


@pytest.mark.asyncio
async def test_l1_hf_ensemble_errors_when_all_members_fail(monkeypatch):
    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content, headers):
            raise httpx.ConnectError("down", request=httpx.Request("POST", url))

    monkeypatch.setattr(
        "app.analyzers.l1_aigen.get_settings",
        lambda: fake_settings(token="tok", models=["m1", "m2"]),
    )
    monkeypatch.setattr("app.hf_inference.httpx.AsyncClient", FakeClient)

    result = await AiGenAnalyzer().analyze(b"img", ClaimContext())
    # error isolation: L1 reports an error, pipeline survives, fusion drops the signal
    assert result.score is None
    assert "all HF ensemble members failed" in result.error
