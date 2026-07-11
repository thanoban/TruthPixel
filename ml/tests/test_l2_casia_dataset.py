from pathlib import Path

from PIL import Image

from ml.layer2_forensics.dataset import assign_splits, discover_casia_v2_samples, summarize_assignments


def _write_image(path: Path, color=(120, 80, 60)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), color).save(path)


def _write_mask(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (32, 32), 255).save(path)


def test_discover_casia_samples_with_masks(tmp_path: Path):
    _write_image(tmp_path / "Au" / "Au_nat_00001.jpg")
    _write_image(tmp_path / "Tp" / "Tp_D_sample_00001.jpg")
    _write_mask(tmp_path / "Gt" / "Tp_D_sample_00001_gt.png")

    samples = discover_casia_v2_samples(tmp_path)

    assert len(samples) == 2
    authentic = next(sample for sample in samples if sample.label == 0)
    tampered = next(sample for sample in samples if sample.label == 1)
    assert authentic.mask_path is None
    assert tampered.mask_path is not None
    assert tampered.mask_path.name == "Tp_D_sample_00001_gt.png"


def test_assign_splits_and_summary_include_mask_counts(tmp_path: Path):
    _write_image(tmp_path / "Au" / "Au_nat_00001.jpg")
    _write_image(tmp_path / "Tp" / "Tp_D_sample_00001.jpg")
    _write_mask(tmp_path / "Gt" / "Tp_D_sample_00001_gt.png")
    _write_image(tmp_path / "Tp" / "Tp_D_sample_00002.jpg")

    assignments = assign_splits(
        discover_casia_v2_samples(tmp_path),
        val_fraction=0.0,
        test_fraction=1.0,
    )
    summary = summarize_assignments(assignments)

    assert all(item.split == "test" for item in assignments)
    assert summary["test"]["total"] == 3
    assert summary["test"]["authentic"] == 1
    assert summary["test"]["tampered"] == 2
    assert summary["test"]["tampered_with_masks"] == 1
