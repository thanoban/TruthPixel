import io
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
from PIL import Image

import app.analyzers.l1_aigen as l1_module
from app.analyzers.l1_aigen import AiGenAnalyzer
from app.schemas import ClaimContext


def make_jpeg(color: tuple[int, int, int] = (120, 80, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
    return buf.getvalue()


def fake_settings(model_path: str = "", device: str = "cpu"):
    return SimpleNamespace(
        l1_model_path=model_path,
        l1_model_device=device,
        hf_api_token="",
        l1_hf_model_list=[],
        l1_hf_ensemble_configured=False,
        hf_inference_timeout_seconds=30.0,
    )


@pytest.fixture(autouse=True)
def clear_runtime_cache():
    l1_module._load_runtime.cache_clear()
    yield
    l1_module._load_runtime.cache_clear()


def write_checkpoint(path: Path) -> None:
    payload = {
        "head_state_dict": {
            "weight": torch.tensor([[2.0, 0.0, 0.0, 0.0]], dtype=torch.float32),
            "bias": torch.tensor([0.0], dtype=torch.float32),
        },
        "metadata": {
            "encoder": {
                "model_name": "ViT-L-14",
                "pretrained": "openai",
                "embedding_dim": 4,
                "device": "cpu",
            },
            "head": {"hidden_dim": 8, "dropout": 0.1, "use_mlp": False},
            "heldout_generators": ["flux", "midjourney"],
            "split_summary": {"train": {"real": 3, "generated": 3}},
            "notes": "unit-test checkpoint",
        },
    }
    torch.save(payload, path)


@pytest.mark.asyncio
async def test_aigen_analyzer_returns_stub_without_model_path(monkeypatch):
    monkeypatch.setattr("app.analyzers.l1_aigen.get_settings", lambda: fake_settings())

    result = await AiGenAnalyzer().analyze(make_jpeg(), ClaimContext())

    assert result.error is None
    assert result.score == 0.5
    assert result.confidence == 0.1
    assert result.evidence["note"] == "stub — neither L1_MODEL_PATH nor an HF ensemble configured"


@pytest.mark.asyncio
async def test_aigen_analyzer_runs_checkpoint_inference(monkeypatch, tmp_path):
    checkpoint_path = tmp_path / "l1_clip_head.pt"
    write_checkpoint(checkpoint_path)

    def fake_preprocess(image: Image.Image):
        assert image.mode == "RGB"
        return torch.ones((3, 2, 2), dtype=torch.float32)

    def fake_encode(tensor):
        return torch.tensor([[0.5, 0.0, 0.0, 0.0]], dtype=torch.float32, device=tensor.device)

    monkeypatch.setattr(
        "app.analyzers.l1_aigen.get_settings",
        lambda: fake_settings(model_path=str(checkpoint_path), device="cpu"),
    )
    monkeypatch.setattr(
        "app.analyzers.l1_aigen.load_open_clip_encoder",
        lambda config: (fake_encode, fake_preprocess),
    )

    result = await AiGenAnalyzer().analyze(make_jpeg(), ClaimContext(order_id="ORD-REAL"))

    assert result.error is None
    assert result.score == pytest.approx(0.7311, abs=1e-4)
    assert result.confidence == pytest.approx(0.4621, abs=1e-4)
    assert result.model_version == "clip-head-ViT-L-14-openai"
    assert result.evidence["prediction"] == "ai_generated"
    assert result.evidence["device"] == "cpu"
    assert result.evidence["heldout_generators"] == ["flux", "midjourney"]
    assert result.evidence["image_size"] == [64, 64]
    assert result.evidence["checkpoint_path"].endswith("l1_clip_head.pt")


@pytest.mark.asyncio
async def test_aigen_analyzer_isolates_missing_checkpoint(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing.pt"
    monkeypatch.setattr(
        "app.analyzers.l1_aigen.get_settings",
        lambda: fake_settings(model_path=str(missing_path), device="cpu"),
    )

    result = await AiGenAnalyzer().analyze(make_jpeg(), ClaimContext())

    assert result.score is None
    assert result.error.startswith("FileNotFoundError: L1 checkpoint not found:")
