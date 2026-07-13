"""Classical image forensics — the no-compute L2 path.

Why this exists: TruFor (the premium L2) needs a heavy upstream Python environment and,
realistically, GPU compute we don't have available right now. But the techniques
government/lab forensic tooling is actually built on are published, classical algorithms
that run in pure numpy/PIL on CPU in well under a second:

- **ELA (Error Level Analysis)** — recompress the image at a known JPEG quality and look
  at where the error is *inconsistent*: a spliced/inpainted region that went through a
  different compression history re-saves differently from the rest of the image.
- **Noise-inconsistency mapping** — natural photos have roughly uniform sensor noise; a
  pasted region carries the noise floor of its *source* image. High-pass residual variance
  per block exposes regions whose noise doesn't match their surroundings.
- **JPEG-ghost detection** — recompress across a sweep of qualities; a region originally
  saved at quality Q shows an error *minimum* near Q. Regions with a different minimum
  than the rest of the image had a different compression history.

None of these match TruFor's accuracy alone — that's why the analyzer reports moderate
confidence and why TruFor supersedes this path the moment it's configured. But three
independent classical signals, averaged, on every claim, beat a neutral stub by a mile,
and they produce a real localization heatmap for the reviewer dashboard using the same
rendering/persistence pipeline TruFor uses.

Calibration honesty: the score mapping below was calibrated against synthetic
splices (see tests/test_forensics_classic.py) — pristine single-compression photos score
low, deliberately spliced ones score high. That is a *sanity* calibration, not a
benchmark; real-world accuracy claims wait for the labeled-claims eval like every other
layer (ML_PLAN.md §4).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

BLOCK_SIZE = 16
ELA_QUALITY = 92
GHOST_QUALITIES = (55, 65, 75, 85, 95)
# Inconsistency -> score mapping: measured on pristine vs. synthetic-splice images.
# Pristine single-compression photos land ~0.05-0.20 combined; splices land ~0.35+.
SCORE_LOW = 0.15
SCORE_HIGH = 0.45


@dataclass(frozen=True, slots=True)
class ClassicForensicsResult:
    score: float
    confidence: float
    anomaly_map: np.ndarray  # block-level [0,1], higher = more suspicious
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
    """Mean-pool a 2D array into (block x block) cells, cropping any remainder."""
    height, width = matrix.shape
    rows = height // block
    cols = width // block
    if rows == 0 or cols == 0:
        return matrix.reshape(1, 1).astype(np.float32) * 0 + float(matrix.mean())
    cropped = matrix[: rows * block, : cols * block]
    return cropped.reshape(rows, block, cols, block).mean(axis=(1, 3))


def _inconsistency(block_map: np.ndarray) -> float:
    """How localized/uneven a block map is, in [0, 1].

    0 = perfectly uniform (whole image behaves the same — no evidence of a region with a
    different processing history); higher = a minority of blocks deviate strongly from
    the typical block, which is the forensic signature of a spliced/edited region.
    Robust ratio of (p95 - median) to p95: scale-free, so it doesn't matter whether the
    raw errors are large or small overall.
    """
    if block_map.size < 4:
        return 0.0
    median = float(np.median(block_map))
    p95 = float(np.percentile(block_map, 95))
    if p95 <= 1e-6:
        return 0.0
    return float(np.clip((p95 - median) / p95, 0.0, 1.0))


def _ela_analysis(image: Image.Image) -> tuple[np.ndarray, float]:
    """Error Level Analysis: |image - recompress(image)| block map + inconsistency."""
    original = _to_gray_f32(image)
    recompressed = _to_gray_f32(_jpeg_roundtrip(image, ELA_QUALITY))
    error = np.abs(original - recompressed)
    block_map = _block_reduce_mean(error, BLOCK_SIZE)
    return block_map, _inconsistency(block_map)


def _noise_analysis(image: Image.Image) -> tuple[np.ndarray, float]:
    """High-pass residual variance per block: mismatched noise floors expose splices."""
    gray = _to_gray_f32(image)
    # 3x3 mean filter via shifted sums (pure numpy — no scipy dependency).
    padded = np.pad(gray, 1, mode="edge")
    smoothed = (
        padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:]
        + padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:]
        + padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
    ) / 9.0
    residual = np.abs(gray - smoothed)
    block_map = _block_reduce_mean(residual, BLOCK_SIZE)
    return block_map, _inconsistency(block_map)


def _ghost_analysis(image: Image.Image) -> tuple[np.ndarray, float]:
    """JPEG ghost: per block, which recompression quality minimizes error.

    Blocks whose best-matching quality differs from the image's dominant one had a
    different compression history. Returns a block map of |best_q_index - modal_q_index|
    normalized to [0,1], plus the fraction of disagreeing blocks as the inconsistency.
    """
    original = _to_gray_f32(image)
    per_quality_errors = []
    for quality in GHOST_QUALITIES:
        recompressed = _to_gray_f32(_jpeg_roundtrip(image, quality))
        error = np.abs(original - recompressed)
        per_quality_errors.append(_block_reduce_mean(error, BLOCK_SIZE))
    stacked = np.stack(per_quality_errors)  # (Q, rows, cols)
    best_quality_index = np.argmin(stacked, axis=0).astype(np.float32)
    modal_index = float(np.bincount(best_quality_index.astype(int).ravel()).argmax())
    deviation = np.abs(best_quality_index - modal_index) / max(1, len(GHOST_QUALITIES) - 1)
    disagreeing_fraction = float((deviation > 0).mean())
    # Fraction alone over-fires on noisy borders; require deviation magnitude too.
    inconsistency = float(np.clip(disagreeing_fraction * deviation[deviation > 0].mean()
                                  if disagreeing_fraction > 0 else 0.0, 0.0, 1.0))
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
    # Map the combined inconsistency onto a fraud score: below SCORE_LOW reads as
    # consistent/authentic-looking, above SCORE_HIGH as strongly manipulated-looking.
    score = float(np.clip((combined - SCORE_LOW) / (SCORE_HIGH - SCORE_LOW), 0.0, 1.0))
    # Classical methods are honest-but-noisy: cap confidence well below TruFor's, and
    # scale with how decisive the evidence is (mid-scores mean "can't tell").
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
