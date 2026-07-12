import io

import numpy as np
from PIL import Image

from app.forensics_classic import run_classic_forensics


def _encode_jpeg(array: np.ndarray, *, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    Image.fromarray(array.astype(np.uint8), mode="RGB").save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    with Image.open(buffer) as image:
        return image.convert("RGB").copy()


def _make_pristine_and_spliced_bytes(size: tuple[int, int] = (160, 160)) -> tuple[bytes, bytes]:
    rng = np.random.default_rng(7)
    base = rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)
    patch = rng.integers(0, 256, size=(48, 48, 3), dtype=np.uint8)

    pristine = _encode_jpeg(base, quality=90)
    patch_image = _encode_jpeg(patch, quality=55)

    spliced = pristine.copy()
    spliced.paste(patch_image.resize((48, 48)), (56, 56))

    pristine_buffer = io.BytesIO()
    pristine.save(pristine_buffer, format="JPEG", quality=90)

    spliced_buffer = io.BytesIO()
    spliced.save(spliced_buffer, format="JPEG", quality=90)
    return pristine_buffer.getvalue(), spliced_buffer.getvalue()


def test_classic_forensics_scores_spliced_image_higher_than_pristine():
    pristine_bytes, spliced_bytes = _make_pristine_and_spliced_bytes()

    pristine = run_classic_forensics(pristine_bytes)
    spliced = run_classic_forensics(spliced_bytes)

    assert pristine.image_size == (160, 160)
    assert spliced.image_size == (160, 160)
    assert pristine.anomaly_map.ndim == 2
    assert spliced.anomaly_map.ndim == 2
    pristine_signal = (
        pristine.ela_inconsistency + pristine.noise_inconsistency + pristine.ghost_inconsistency
    )
    spliced_signal = (
        spliced.ela_inconsistency + spliced.noise_inconsistency + spliced.ghost_inconsistency
    )
    assert 0.0 <= pristine.score <= 1.0
    assert 0.0 <= spliced.score <= 1.0
    assert spliced_signal > pristine_signal
    assert spliced.ela_inconsistency >= pristine.ela_inconsistency
