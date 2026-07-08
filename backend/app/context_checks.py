from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True, slots=True)
class ImageFingerprint:
    average_hash: int
    histogram: tuple[float, ...]


def _popcount(value: int) -> int:
    return value.bit_count()


def average_hash(image: Image.Image, size: int = 8) -> int:
    grayscale = image.convert("L").resize((size, size), Image.Resampling.BICUBIC)
    pixels = list(grayscale.tobytes())
    avg = sum(pixels) / len(pixels)
    bits = 0
    for pixel in pixels:
        bits = (bits << 1) | int(pixel >= avg)
    return bits


def normalized_histogram(image: Image.Image, bins_per_channel: int = 8) -> tuple[float, ...]:
    rgb = image.convert("RGB").resize((128, 128), Image.Resampling.BICUBIC)
    histogram = rgb.histogram()
    grouped: list[float] = []
    bucket_size = max(1, 256 // bins_per_channel)
    for channel in range(3):
        channel_values = histogram[channel * 256 : (channel + 1) * 256]
        for idx in range(0, 256, bucket_size):
            grouped.append(float(sum(channel_values[idx : idx + bucket_size])))
    norm = math.sqrt(sum(value * value for value in grouped)) or 1.0
    return tuple(value / norm for value in grouped)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("histograms must have matching lengths")
    return sum(a * b for a, b in zip(left, right))


def fingerprint_bytes(image_bytes: bytes) -> ImageFingerprint:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return ImageFingerprint(
        average_hash=average_hash(image),
        histogram=normalized_histogram(image),
    )


def hash_similarity(left: int, right: int, bits: int = 64) -> float:
    distance = _popcount(left ^ right)
    return max(0.0, 1.0 - (distance / bits))


def combined_similarity(left: ImageFingerprint, right: ImageFingerprint) -> float:
    hash_score = hash_similarity(left.average_hash, right.average_hash)
    hist_score = cosine_similarity(left.histogram, right.histogram)
    # Product-photo matching cares about palette and surface distribution as much as
    # structure, so histogram evidence should outweigh grayscale aHash on simple scenes.
    return max(0.0, min(1.0, (hash_score * 0.4) + (hist_score * 0.6)))
