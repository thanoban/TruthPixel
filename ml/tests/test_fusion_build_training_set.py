import json
from pathlib import Path

from PIL import Image

from ml.datagen.fraud_pairs import generate_dataset
from ml.fusion.build_training_set import build_training_examples


def _write_source(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (128, 128), color)
    for y in range(128):
        for x in range(128):
            image.putpixel((x, y), ((color[0] + x) % 255, (color[1] + y) % 255, color[2]))
    image.save(path)


def test_build_training_examples_from_fraud_pairs(tmp_path: Path):
    input_root = tmp_path / "input"
    dataset_root = tmp_path / "fraud_pairs"
    output_path = tmp_path / "fusion_train.jsonl"
    _write_source(input_root / "listing-1.jpg", (80, 120, 160))
    _write_source(input_root / "listing-2.jpg", (180, 90, 70))

    generate_dataset(input_root, dataset_root, seed=13, val_fraction=0.0, test_fraction=1.0)
    summary = build_training_examples(
        dataset_root,
        dataset_root / "manifest.jsonl",
        output_path,
    )

    assert summary == {"rows": 4, "positives": 2, "negatives": 2}
    rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4
    assert {row["label"] for row in rows} == {0, 1}
    assert all("signals" in row for row in rows)
    assert all("source" in row for row in rows)
    assert all(row["source"]["dataset_split"] == "test" for row in rows)
    assert all(len(row["signals"]) == 5 for row in rows)
