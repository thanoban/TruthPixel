"""Frozen CLIP embeddings for L5 context similarity — the v1 upgrade path.

L5 v0 (`context_checks.py`) compares images with a perceptual hash + color histogram —
cheap, dependency-free, but blind to semantic similarity (crops, angle changes, lighting).
L5 v1 blends in a **frozen, pretrained CLIP embedding** cosine similarity: no training,
just inference, reusing the same `open_clip` loader as L1's checkpoint mode
(`ml/layer1_aigen/model.py::load_open_clip_encoder`). Independent architecture/features
from the hash+histogram signal, so blending the two is itself a small fusion, consistent
with the rest of this system.

Degrades gracefully: if `torch`/`open_clip_torch` aren't installed, or the model fails to
load, callers catch `EmbeddingUnavailable` and fall back to hash+histogram-only — L5 must
never fail a claim just because the embedding path is unavailable.
"""

from __future__ import annotations

import io
from functools import lru_cache
from types import SimpleNamespace

from PIL import Image


class EmbeddingUnavailable(RuntimeError):
    """Raised when the embedding encoder can't be loaded or run."""


@lru_cache(maxsize=2)
def _load_encoder(model_name: str, pretrained: str, device: str):
    from ml.layer1_aigen.model import load_open_clip_encoder

    try:
        return load_open_clip_encoder(
            SimpleNamespace(model_name=model_name, pretrained=pretrained, device=device)
        )
    except RuntimeError as exc:
        raise EmbeddingUnavailable(str(exc)) from exc


def embed_image_bytes(
    image_bytes: bytes, *, model_name: str, pretrained: str, device: str
) -> "list[float]":
    """Return an L2-normalized embedding as a plain list (JSON/evidence-friendly)."""
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised in minimal environments
        raise EmbeddingUnavailable("PyTorch is required for L5 embeddings.") from exc

    encode, preprocess = _load_encoder(model_name, pretrained, device)
    try:
        with Image.open(io.BytesIO(image_bytes)) as pil_image:
            image_rgb = pil_image.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingUnavailable(f"unable to decode image for embedding: {exc}") from exc

    tensor = preprocess(image_rgb).unsqueeze(0).to(device)
    with torch.no_grad():
        features = encode(tensor)
    return features.squeeze(0).to("cpu").tolist()


def cosine_similarity_01(left: list[float], right: list[float]) -> float:
    """Cosine similarity rescaled from [-1, 1] to [0, 1] to match the hash/histogram scale."""
    if len(left) != len(right):
        raise ValueError("embeddings must have matching dimensionality")
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    denom = (norm_left * norm_right) or 1.0
    cosine = max(-1.0, min(1.0, dot / denom))
    return (cosine + 1.0) / 2.0


def reset_embedding_cache() -> None:
    _load_encoder.cache_clear()
