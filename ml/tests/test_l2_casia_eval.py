import io
from pathlib import Path

import numpy as np
from PIL import Image

from ml.layer2_forensics.eval import _localization_metrics, _resize_probability_map, evaluate


def _write_rgb(path: Path, color=(100, 120, 160)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), color).save(path)


def _write_mask(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    mask = Image.new("L", (32, 32), 0)
    for y in range(12, 24):
        for x in range(12, 24):
            mask.putpixel((x, y), 255)
    mask.save(path)


def test_resize_probability_map_returns_image_sized_matrix():
    block_map = np.array([[0.0, 1.0], [0.25, 0.75]], dtype=np.float32)

    resized = _resize_probability_map(block_map, (32, 16))

    assert resized.shape == (16, 32)
    assert 0.0 <= float(resized.min()) <= 1.0
    assert 0.0 <= float(resized.max()) <= 1.0


def test_localization_metrics_scores_overlap():
    probability = np.zeros((4, 4), dtype=np.float32)
    probability[1:3, 1:3] = 0.9
    mask = np.zeros((4, 4), dtype=bool)
    mask[1:3, 1:3] = True

    metrics = _localization_metrics(probability, mask, threshold=0.5)

    assert metrics.intersection_over_union == 1.0
    assert metrics.f1 == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0


def test_evaluate_writes_report_for_casia_layout(tmp_path: Path, monkeypatch):
    _write_rgb(tmp_path / "Au" / "Au_nat_00001.jpg", color=(100, 120, 160))
    _write_rgb(tmp_path / "Tp" / "Tp_D_sample_00001.jpg", color=(210, 50, 60))
    _write_mask(tmp_path / "Gt" / "Tp_D_sample_00001_gt.png")
    report_path = tmp_path / "report.json"

    class FakeResult:
        def __init__(self, score: float, anomaly_map: np.ndarray):
            self.score = score
            self.confidence = 0.35
            self.anomaly_map = anomaly_map
            self.image_size = (32, 32)

    def fake_run_classic_forensics(image_bytes: bytes):
        opened = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if opened.getpixel((0, 0))[0] > 150:
            return FakeResult(0.9, np.array([[0.0, 0.0], [0.0, 1.0]], dtype=np.float32))
        return FakeResult(0.1, np.zeros((2, 2), dtype=np.float32))

    monkeypatch.setattr("ml.layer2_forensics.eval.run_classic_forensics", fake_run_classic_forensics)

    result = evaluate(
        type(
            "Args",
            (),
            {
                "data_root": str(tmp_path),
                "report_path": str(report_path),
                "eval_split": "test",
                "val_fraction": 0.0,
                "test_fraction": 1.0,
                "localization_threshold": 0.5,
            },
        )()
    )

    assert report_path.exists()
    assert result["dataset"] == "CASIA v2"
    assert result["evaluation"]["count"] == 2
    assert result["evaluation"]["tampered_count"] == 1
    assert result["evaluation"]["localization"]["count"] == 1
