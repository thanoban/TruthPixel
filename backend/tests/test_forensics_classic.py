import io

import numpy as np
from PIL import Image, ImageDraw

from app.forensics_classic import run_classic_forensics


def _make_pristine_jpeg() -> bytes:
    image = Image.new("RGB", (256, 256), (92, 128, 172))
    for y in range(256):
        for x in range(256):
            image.putpixel((x, y), (80 + x // 2, 60 + y // 2, 100 + (x + y) // 4))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _make_synthetic_splice() -> bytes:
    base = Image.open(io.BytesIO(_make_pristine_jpeg())).convert("RGB")
    overlay = Image.new("RGB", (80, 80), (245, 240, 35))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((10, 10, 70, 70), fill=(220, 35, 60))
    overlay_buffer = io.BytesIO()
    overlay.save(overlay_buffer, format="JPEG", quality=65)
    overlay_region = Image.open(io.BytesIO(overlay_buffer.getvalue())).convert("RGB")
    base.paste(overlay_region, (120, 96))
    output = io.BytesIO()
    base.save(output, format="JPEG", quality=92)
    return output.getvalue()


def test_classic_forensics_localizes_synthetic_splice_region():
    pristine = run_classic_forensics(_make_pristine_jpeg())
    spliced = run_classic_forensics(_make_synthetic_splice())

    assert pristine.confidence >= 0.25
    assert spliced.confidence >= 0.25
    assert spliced.anomaly_map.ndim == 2
    assert spliced.anomaly_map.max() <= 1.0
    assert spliced.anomaly_map.min() >= 0.0
    assert 0.0 <= pristine.score <= 1.0
    assert 0.0 <= spliced.score <= 1.0

    # The synthetic patch is pasted at roughly x=[128, 200), y=[96, 168), which maps
    # to block rows 6:11 and columns 8:13 for the 16x16 block grid.
    splice_region = spliced.anomaly_map[6:11, 8:13]
    assert splice_region.shape == (5, 5)
    assert float(splice_region.mean()) > float(spliced.anomaly_map.mean()) * 4
    assert float(splice_region.max()) > 0.95
    assert not np.allclose(pristine.anomaly_map[6:11, 8:13], splice_region)


def test_classic_forensics_reports_image_size():
    result = run_classic_forensics(_make_pristine_jpeg())

    assert result.image_size == (256, 256)
    assert 0.0 <= result.ela_inconsistency <= 1.0
    assert 0.0 <= result.noise_inconsistency <= 1.0
    assert 0.0 <= result.ghost_inconsistency <= 1.0
