"""Classical image forensics — the no-compute L2 path."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

BLOCK_SIZE = 16
ELA_QUALITY = 92
GHOST_QUALITIES = (55, 65, 75, 85, 95)
SCORE_LOW = 0.15
SCORE_HIGH = 0.45


@dataclass(frozen=True, slots=True)
class ClassicForensicsResult:
    score: float
    confidence: float
    anomaly_map: np.ndarray
    ela_inconsistency: float
    noise_inconsistency: float
    ghost_inconsistency: float
    image_size: tuple[int, int]


def _to_gray_f32(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32)


def _jpeg_roundtrip(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    with Image.open(buffer) as reloaded:
        return reloaded.convert("RGB").copy()


def _block_reduce_mean(matrix: np.ndarray, block: int) -> np.ndarray:
    height, width = matrix.shape
    rows = height // block
    cols = width // block
    if rows == 0 or cols == 0:
        return matrix.reshape(1, 1).astype(np.float32) * 0 + float(matrix.mean())
    cropped = matrix[: rows * block, : cols * block]
    return cropped.reshape(rows, block, cols, block).mean(axis=(1, 3))


def _inconsistency(block_map: np.ndarray) -> float:
    if block_map.size < 4:
        return 0.0
    median = float(np.median(block_map))
    p95 = float(np.percentile(block_map, 95))
    if p95 <= 1e-6:
        return 0.0
    return float(np.clip((p95 - median) / p95, 0.0, 1.0))


def _ela_analysis(image: Image.Image) -> tuple[np.ndarray, float]:
    original = _to_gray_f32(image)
    recompressed = _to_gray_f32(_jpeg_roundtrip(image, ELA_QUALITY))
    error = np.abs(original - recompressed)
    block_map = _block_reduce_mean(error, BLOCK_SIZE)
    return block_map, _inconsistency(block_map)


def _noise_analysis(image: Image.Image) -> tuple[np.ndarray, float]:
    gray = _to_gray_f32(image)
    padded = np.pad(gray, 1, mode="edge")
    smoothed = (
        padded[:-2, :-2]
        + padded[:-2, 1:-1]
        + padded[:-2, 2:]
        + padded[1:-1, :-2]
        + padded[1:-1, 1:-1]
        + padded[1:-1, 2:]
        + padded[2:, :-2]
        + padded[2:, 1:-1]
        + padded[2:, 2:]
    ) / 9.0
    residual = np.abs(gray - smoothed)
    block_map = _block_reduce_mean(residual, BLOCK_SIZE)
    return block_map, _inconsistency(block_map)


def _ghost_analysis(image: Image.Image) -> tuple[np.ndarray, float]:
    original = _to_gray_f32(image)
    per_quality_errors = []
    for quality in GHOST_QUALITIES:
        recompressed = _to_gray_f32(_jpeg_roundtrip(image, quality))
        error = np.abs(original - recompressed)
        per_quality_errors.append(_block_reduce_mean(error, BLOCK_SIZE))
    stacked = np.stack(per_quality_errors)
    best_quality_index = np.argmin(stacked, axis=0).astype(np.float32)
    modal_index = float(np.bincount(best_quality_index.astype(int).ravel()).argmax())
    deviation = np.abs(best_quality_index - modal_index) / max(1, len(GHOST_QUALITIES) - 1)
    disagreeing_fraction = float((deviation > 0).mean())
    inconsistency = float(
        np.clip(
            disagreeing_fraction * deviation[deviation > 0].mean()
            if disagreeing_fraction > 0
            else 0.0,
            0.0,
            1.0,
        )
    )
    return deviation, inconsistency


def _normalize_map(block_map: np.ndarray) -> np.ndarray:
    high = float(block_map.max())
    if high <= 1e-6:
        return np.zeros_like(block_map, dtype=np.float32)
    return (block_map / high).astype(np.float32)


def run_classic_forensics(image_bytes: bytes) -> ClassicForensicsResult:
    with Image.open(io.BytesIO(image_bytes)) as pil_image:
        image = pil_image.convert("RGB").copy()

    ela_map, ela_score = _ela_analysis(image)
    noise_map, noise_score = _noise_analysis(image)
    ghost_map, ghost_score = _ghost_analysis(image)

    combined = (ela_score + noise_score + ghost_score) / 3.0
    score = float(np.clip((combined - SCORE_LOW) / (SCORE_HIGH - SCORE_LOW), 0.0, 1.0))
    confidence = round(0.25 + 0.25 * abs(score - 0.5) * 2, 4)
    anomaly = _normalize_map(
        _normalize_map(ela_map) + _normalize_map(noise_map) + _normalize_map(ghost_map)
    )

    return ClassicForensicsResult(
        score=round(score, 4),
        confidence=confidence,
        anomaly_map=anomaly,
        ela_inconsistency=round(ela_score, 4),
        noise_inconsistency=round(noise_score, 4),
        ghost_inconsistency=round(ghost_score, 4),
        image_size=image.size,
    )
