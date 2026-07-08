import random

from PIL import Image

from ml.layer1_aigen.augment import (
    ScreenshotAugmentConfig,
    ScreenshotAugmentor,
    build_robustness_variants,
)


def test_screenshot_augmentor_returns_nonempty_rgb_image():
    image = Image.new("RGB", (96, 72), (120, 40, 200))
    augmentor = ScreenshotAugmentor(
        ScreenshotAugmentConfig(
            apply_probability=1.0,
            blur_probability=1.0,
            ui_strip_probability=1.0,
        )
    )

    augmented = augmentor(image, rng=random.Random(7))

    assert augmented.mode == "RGB"
    assert augmented.size[0] >= 8
    assert augmented.size[1] >= 8


def test_build_robustness_variants_returns_expected_keys():
    image = Image.new("RGB", (80, 80), (10, 120, 200))

    variants = build_robustness_variants(image)

    assert set(variants) == {"pristine", "jpeg_q75", "screenshot_sim", "social_roundtrip"}
    assert all(variant.mode == "RGB" for variant in variants.values())
