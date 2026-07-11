import json
from pathlib import Path

from PIL import Image

from ml.datagen.fraud_pairs import generate_dataset
from ml.fusion.robustness_eval import evaluate_fraud_pairs


def _write_source(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (128, 128), color)
    for y in range(128):
        for x in range(128):
            image.putpixel((x, y), ((color[0] + x) % 255, (color[1] + y) % 255, color[2]))
    image.save(path)


def test_evaluate_fraud_pairs_writes_variant_report(tmp_path: Path):
    input_root = tmp_path / "input"
    dataset_root = tmp_path / "fraud_pairs"
    report_path = tmp_path / "robustness.json"
    _write_source(input_root / "listing-1.jpg", (80, 120, 160))
    _write_source(input_root / "listing-2.jpg", (180, 90, 70))

    generate_dataset(input_root, dataset_root, seed=19, val_fraction=0.0, test_fraction=1.0)
    report = evaluate_fraud_pairs(
        dataset_root,
        dataset_root / "manifest.jsonl",
        report_path,
        limit=4,
    )

    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["dataset"] == "fraud_pairs"
    assert set(payload["variants"]) == {"pristine", "jpeg_q75", "screenshot_sim", "social_roundtrip"}
    for variant_name, variant_payload in payload["variants"].items():
        assert variant_payload["metrics"]["count"] == 4
        assert "fused_auroc" in variant_payload["metrics"]
        assert "l2_auroc" in variant_payload["metrics"]
        assert len(variant_payload["samples"]) == 4
        assert all(sample["variant"] == variant_name for sample in variant_payload["samples"])
