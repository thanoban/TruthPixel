from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class EncoderConfig:
    model_name: str = "ViT-L-14"
    pretrained: str = "openai"
    embedding_dim: int = 768
    device: str = "cpu"


@dataclass(slots=True)
class HeadConfig:
    hidden_dim: int = 512
    dropout: float = 0.2
    use_mlp: bool = True


@dataclass(slots=True)
class CheckpointMetadata:
    encoder: EncoderConfig
    head: HeadConfig
    heldout_generators: list[str]
    split_summary: dict[str, dict[str, int]]
    notes: str = ""


def _require_torch():
    try:
        import torch
        from torch import nn
    except ImportError as exc:  # pragma: no cover - exercised in CLI usage
        raise RuntimeError(
            "PyTorch is required for the L1 training scaffold. Install ml/requirements.txt."
        ) from exc
    return torch, nn


class LinearProbeHeadProxy:
    """Factory wrapper so importing this module doesn't require torch immediately."""

    @staticmethod
    def build(input_dim: int):
        torch, nn = _require_torch()
        return nn.Linear(input_dim, 1)


class MlpProbeHeadProxy:
    @staticmethod
    def build(input_dim: int, config: HeadConfig):
        torch, nn = _require_torch()
        return nn.Sequential(
            nn.Linear(input_dim, config.hidden_dim),
            nn.GELU(),
            nn.Dropout(config.dropout),
            nn.Linear(config.hidden_dim, 1),
        )


def build_probe_head(input_dim: int, config: HeadConfig):
    if config.use_mlp:
        return MlpProbeHeadProxy.build(input_dim, config)
    return LinearProbeHeadProxy.build(input_dim)


def load_open_clip_encoder(config: EncoderConfig):
    torch, _ = _require_torch()
    try:
        import open_clip
    except ImportError as exc:  # pragma: no cover - exercised in CLI usage
        raise RuntimeError(
            "open_clip_torch is required for the L1 scaffold. Install ml/requirements.txt."
        ) from exc

    model, _, preprocess = open_clip.create_model_and_transforms(
        config.model_name, pretrained=config.pretrained
    )
    model.eval()
    model.to(config.device)
    for parameter in model.parameters():
        parameter.requires_grad = False

    def encode(images):
        with torch.no_grad():
            features = model.encode_image(images)
            return features / features.norm(dim=-1, keepdim=True).clamp_min(1e-6)

    return encode, preprocess


def save_checkpoint(
    path: str | Path,
    *,
    head_state_dict: dict[str, Any],
    metadata: CheckpointMetadata,
) -> None:
    torch, _ = _require_torch()
    payload = {
        "head_state_dict": head_state_dict,
        "metadata": asdict(metadata),
    }
    torch.save(payload, path)


def write_metadata_json(path: str | Path, metadata: CheckpointMetadata) -> None:
    Path(path).write_text(json.dumps(asdict(metadata), indent=2), encoding="utf-8")
