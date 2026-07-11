import json
from pathlib import Path

import numpy as np
from PIL import Image

from ml.datagen.fraud_pairs import discover_source_images, generate_dataset


def _write_source(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (128, 128), color)
    for y in range(128):
        for x in range(128):
            image.putpixel((x, y), ((color[0] + x) % 255, (color[1] + y) % 255, color[2]))
    image.save(path)


def test_discover_source_images_finds_supported_files(tmp_path: Path):
    _write_source(tmp_path / "a.jpg", (80, 120, 160))
    _write_source(tmp_path / "nested" / "b.png", (130, 90, 60))
    (tmp_path / "skip.txt").write_text("nope", encoding="utf-8")

    images = discover_source_images(tmp_path)

    assert [path.name for path in images] == ["a.jpg", "b.png"]


def test_generate_dataset_writes_pairs_masks_and_manifest(tmp_path: Path):
    input_root = tmp_path / "input"
    output_root = tmp_path / "output"
    _write_source(input_root / "listing-1.jpg", (80, 120, 160))
    _write_source(input_root / "listing-2.jpg", (180, 90, 70))

    summary = generate_dataset(input_root, output_root, seed=11, val_fraction=0.0, test_fraction=1.0)

    assert summary["source_images"] == 2
    assert summary["total_examples"] == 4
    assert summary["clean_examples"] == 2
    assert summary["fraud_examples"] == 2
    manifest_path = output_root / "manifest.jsonl"
    assert manifest_path.exists()

    records = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 4
    assert {record["label"] for record in records} == {0, 1}
    assert all(record["split"] == "test" for record in records)

    fraud_records = [record for record in records if record["label"] == 1]
    assert all(record["mask_image"] for record in fraud_records)
    assert all("synthetic_splice_damage_patch" in record["operations"] for record in fraud_records)

    for record in fraud_records:
        mask = Image.open(output_root / record["mask_image"])
        assert np.asarray(mask).max() > 0

    clean_records = [record for record in records if record["label"] == 0]
    assert all(record["mask_image"] is None for record in clean_records)
    assert all(record["pair_kind"] == "clean_claim" for record in clean_records)


def test_generate_dataset_is_deterministic_for_manifest_content(tmp_path: Path):
    input_root = tmp_path / "input"
    _write_source(input_root / "listing-1.jpg", (80, 120, 160))
    _write_source(input_root / "listing-2.jpg", (180, 90, 70))

    first = tmp_path / "first"
    second = tmp_path / "second"
    generate_dataset(input_root, first, seed=17, val_fraction=0.0, test_fraction=1.0)
    generate_dataset(input_root, second, seed=17, val_fraction=0.0, test_fraction=1.0)

    assert (first / "manifest.jsonl").read_text(encoding="utf-8") == (
        second / "manifest.jsonl"
    ).read_text(encoding="utf-8")
