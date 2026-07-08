from pathlib import Path

from PIL import Image

from ml.layer1_aigen.dataset import assign_splits, discover_samples, summarize_assignments


def _write_image(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 24), (200, 60, 60)).save(path)


def test_discover_samples_and_assign_heldout_generators(tmp_path: Path):
    _write_image(tmp_path / "real" / "phone" / "real-1.jpg")
    _write_image(tmp_path / "generated" / "sdxl" / "gen-1.jpg")
    _write_image(tmp_path / "generated" / "glide" / "gen-2.jpg")

    records = discover_samples(tmp_path)
    assignments = assign_splits(
        records,
        heldout_generators={"sdxl"},
        val_fraction=0.0,
        test_fraction=0.0,
    )
    summary = summarize_assignments(assignments)

    assert len(records) == 3
    assert any(item.record.generator == "sdxl" and item.split == "test" for item in assignments)
    assert any(item.record.generator == "glide" and item.split == "train" for item in assignments)
    assert summary["test"]["generated"] == 1


def test_real_samples_default_to_camera_generator(tmp_path: Path):
    _write_image(tmp_path / "real" / "marketplace" / "capture.jpg")

    records = discover_samples(tmp_path)

    assert len(records) == 1
    assert records[0].generator == "camera"
    assert records[0].label == 0
