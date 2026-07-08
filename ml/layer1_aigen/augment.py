from __future__ import annotations

import io
import random
from dataclasses import dataclass

from PIL import Image, ImageFilter


@dataclass(slots=True)
class ScreenshotAugmentConfig:
    apply_probability: float = 0.5
    resize_min_scale: float = 0.5
    resize_max_scale: float = 1.5
    jpeg_quality_min: int = 65
    jpeg_quality_max: int = 95
    jpeg_roundtrips_min: int = 1
    jpeg_roundtrips_max: int = 2
    crop_min_scale: float = 0.85
    crop_max_scale: float = 1.0
    blur_probability: float = 0.2
    blur_radius_min: float = 0.3
    blur_radius_max: float = 1.0
    ui_strip_probability: float = 0.1
    ui_strip_max_ratio: float = 0.12


def _clamp_dimension(value: int) -> int:
    return max(8, int(round(value)))


def _jpeg_roundtrip(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    return Image.open(buffer).convert("RGB")


def _random_rescale(image: Image.Image, scale: float) -> Image.Image:
    width, height = image.size
    resized = image.resize(
        (_clamp_dimension(width * scale), _clamp_dimension(height * scale)),
        resample=Image.Resampling.BICUBIC,
    )
    return resized


def _random_crop(image: Image.Image, rng: random.Random, min_scale: float, max_scale: float) -> Image.Image:
    width, height = image.size
    scale = rng.uniform(min_scale, max_scale)
    crop_w = min(width, _clamp_dimension(width * scale))
    crop_h = min(height, _clamp_dimension(height * scale))
    if crop_w == width and crop_h == height:
        return image
    left = 0 if crop_w == width else rng.randint(0, width - crop_w)
    top = 0 if crop_h == height else rng.randint(0, height - crop_h)
    return image.crop((left, top, left + crop_w, top + crop_h))


def _simulate_ui_strip(image: Image.Image, rng: random.Random, max_ratio: float) -> Image.Image:
    width, height = image.size
    max_crop_x = max(0, int(width * max_ratio))
    max_crop_y = max(0, int(height * max_ratio))
    left = rng.randint(0, max_crop_x) if max_crop_x else 0
    right = rng.randint(0, max_crop_x) if max_crop_x else 0
    top = rng.randint(0, max_crop_y) if max_crop_y else 0
    bottom = rng.randint(0, max_crop_y) if max_crop_y else 0
    if left + right >= width - 8:
        right = max(0, width - 9 - left)
    if top + bottom >= height - 8:
        bottom = max(0, height - 9 - top)
    return image.crop((left, top, width - right, height - bottom))


class ScreenshotAugmentor:
    """Approximate screenshot/re-save degradation for robust L1 training."""

    def __init__(self, config: ScreenshotAugmentConfig | None = None):
        self.config = config or ScreenshotAugmentConfig()

    def __call__(self, image: Image.Image, rng: random.Random | None = None) -> Image.Image:
        rng = rng or random.Random()
        image = image.convert("RGB")
        if rng.random() > self.config.apply_probability:
            return image

        steps = ["resize", "jpeg", "crop"]
        if rng.random() < self.config.blur_probability:
            steps.append("blur")
        if rng.random() < self.config.ui_strip_probability:
            steps.append("ui_strip")
        rng.shuffle(steps)

        augmented = image
        for step in steps:
            if step == "resize":
                scale = rng.uniform(self.config.resize_min_scale, self.config.resize_max_scale)
                augmented = _random_rescale(augmented, scale)
            elif step == "jpeg":
                rounds = rng.randint(
                    self.config.jpeg_roundtrips_min, self.config.jpeg_roundtrips_max
                )
                for _ in range(rounds):
                    quality = rng.randint(
                        self.config.jpeg_quality_min, self.config.jpeg_quality_max
                    )
                    augmented = _jpeg_roundtrip(augmented, quality)
            elif step == "crop":
                augmented = _random_crop(
                    augmented, rng, self.config.crop_min_scale, self.config.crop_max_scale
                )
            elif step == "blur":
                radius = rng.uniform(
                    self.config.blur_radius_min, self.config.blur_radius_max
                )
                augmented = augmented.filter(ImageFilter.GaussianBlur(radius=radius))
            elif step == "ui_strip":
                augmented = _simulate_ui_strip(
                    augmented, rng, self.config.ui_strip_max_ratio
                )

        return augmented


def build_robustness_variants(image: Image.Image) -> dict[str, Image.Image]:
    """Produce repeatable eval perturbations mirroring the ML plan."""

    pristine = image.convert("RGB")
    augmentor = ScreenshotAugmentor(
        ScreenshotAugmentConfig(
            apply_probability=1.0,
            resize_min_scale=0.8,
            resize_max_scale=1.1,
            jpeg_quality_min=72,
            jpeg_quality_max=78,
            jpeg_roundtrips_min=1,
            jpeg_roundtrips_max=1,
            crop_min_scale=0.9,
            crop_max_scale=0.98,
            blur_probability=0.2,
            ui_strip_probability=0.15,
        )
    )
    rng = random.Random(1337)
    screenshot_sim = augmentor(pristine, rng=rng)
    social_roundtrip = _jpeg_roundtrip(_jpeg_roundtrip(pristine, quality=80), quality=72)
    return {
        "pristine": pristine,
        "jpeg_q75": _jpeg_roundtrip(pristine, quality=75),
        "screenshot_sim": screenshot_sim,
        "social_roundtrip": social_roundtrip,
    }
