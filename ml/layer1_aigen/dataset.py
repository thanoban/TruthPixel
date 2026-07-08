from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True, slots=True)
class SampleRecord:
    path: Path
    label: int
    generator: str
    source_group: str


@dataclass(frozen=True, slots=True)
class AssignedSample:
    record: SampleRecord
    split: str


def _stable_fraction(value: str) -> float:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _iter_image_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def discover_samples(root: str | Path) -> list[SampleRecord]:
    """Discover samples from root/real/* and root/generated/* layouts."""

    root = Path(root)
    samples: list[SampleRecord] = []
    for label_name, label_value in (("real", 0), ("generated", 1)):
        label_root = root / label_name
        if not label_root.exists():
            continue
        for image_path in _iter_image_files(label_root):
            relative = image_path.relative_to(label_root)
            parts = relative.parts
            group = parts[0] if len(parts) > 1 else "default"
            generator = "camera" if label_name == "real" else group.lower()
            samples.append(
                SampleRecord(
                    path=image_path,
                    label=label_value,
                    generator=generator,
                    source_group=group.lower(),
                )
            )
    return samples


def assign_splits(
    records: list[SampleRecord],
    *,
    heldout_generators: set[str] | None = None,
    val_fraction: float = 0.1,
    test_fraction: float = 0.1,
) -> list[AssignedSample]:
    heldout_generators = {g.lower() for g in (heldout_generators or set())}
    assignments: list[AssignedSample] = []
    for record in records:
        if record.label == 1 and record.generator.lower() in heldout_generators:
            split = "test"
        else:
            bucket = _stable_fraction(str(record.path))
            if bucket < val_fraction:
                split = "val"
            elif bucket < val_fraction + test_fraction:
                split = "test"
            else:
                split = "train"
        assignments.append(AssignedSample(record=record, split=split))
    return assignments


def summarize_assignments(assignments: list[AssignedSample]) -> dict[str, dict[str, int]]:
    summary = {
        "train": {"total": 0, "real": 0, "generated": 0},
        "val": {"total": 0, "real": 0, "generated": 0},
        "test": {"total": 0, "real": 0, "generated": 0},
    }
    for item in assignments:
        split = summary[item.split]
        split["total"] += 1
        if item.record.label == 0:
            split["real"] += 1
        else:
            split["generated"] += 1
    return summary


class ImageRecordDataset:
    """Lightweight PIL dataset wrapper usable from train/eval scripts."""

    def __init__(self, assignments: list[AssignedSample], split: str):
        self.items = [item for item in assignments if item.split == split]

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int) -> tuple[Image.Image, int, AssignedSample]:
        item = self.items[index]
        image = Image.open(item.record.path).convert("RGB")
        return image, item.record.label, item
