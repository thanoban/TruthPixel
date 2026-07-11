from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True, slots=True)
class CasiaSample:
    image_path: Path
    label: int
    sample_id: str
    mask_path: Path | None = None


@dataclass(frozen=True, slots=True)
class AssignedCasiaSample:
    sample: CasiaSample
    split: str


def _stable_fraction(value: str) -> float:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _iter_image_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def _find_dataset_dir(root: Path, *candidates: str) -> Path | None:
    for candidate in candidates:
        path = root / candidate
        if path.exists():
            return path
    return None


def _build_mask_index(mask_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for path in _iter_image_files(mask_root):
        stem = path.stem.lower()
        if stem.endswith("_gt"):
            stem = stem[:-3]
        index[stem] = path
    return index


def discover_casia_v2_samples(root: str | Path) -> list[CasiaSample]:
    """Discover CASIA v2 samples from an Au/Tp/Gt-style checkout.

    Expected roots:
    - `Au/` authentic images
    - `Tp/` tampered images
    - `Gt/` or `Groundtruth/` masks named like `<tampered_stem>_gt.png`
    """

    dataset_root = Path(root)
    authentic_root = _find_dataset_dir(dataset_root, "Au", "au")
    tampered_root = _find_dataset_dir(dataset_root, "Tp", "tp")
    mask_root = _find_dataset_dir(dataset_root, "Gt", "gt", "Groundtruth", "groundtruth")
    if authentic_root is None or tampered_root is None:
        raise RuntimeError(
            "CASIA v2 root must contain Au/ and Tp/ directories."
        )

    mask_index = _build_mask_index(mask_root) if mask_root is not None else {}
    samples: list[CasiaSample] = []
    for image_path in _iter_image_files(authentic_root):
        samples.append(
            CasiaSample(
                image_path=image_path,
                label=0,
                sample_id=image_path.stem.lower(),
            )
        )
    for image_path in _iter_image_files(tampered_root):
        sample_id = image_path.stem.lower()
        samples.append(
            CasiaSample(
                image_path=image_path,
                label=1,
                sample_id=sample_id,
                mask_path=mask_index.get(sample_id),
            )
        )
    return samples


def assign_splits(
    samples: list[CasiaSample],
    *,
    val_fraction: float = 0.1,
    test_fraction: float = 0.2,
) -> list[AssignedCasiaSample]:
    assignments: list[AssignedCasiaSample] = []
    for sample in samples:
        bucket = _stable_fraction(sample.sample_id)
        if bucket < val_fraction:
            split = "val"
        elif bucket < val_fraction + test_fraction:
            split = "test"
        else:
            split = "train"
        assignments.append(AssignedCasiaSample(sample=sample, split=split))
    return assignments


def summarize_assignments(assignments: list[AssignedCasiaSample]) -> dict[str, dict[str, int]]:
    summary = {
        "train": {"total": 0, "authentic": 0, "tampered": 0, "tampered_with_masks": 0},
        "val": {"total": 0, "authentic": 0, "tampered": 0, "tampered_with_masks": 0},
        "test": {"total": 0, "authentic": 0, "tampered": 0, "tampered_with_masks": 0},
    }
    for item in assignments:
        slot = summary[item.split]
        slot["total"] += 1
        if item.sample.label == 0:
            slot["authentic"] += 1
        else:
            slot["tampered"] += 1
            if item.sample.mask_path is not None:
                slot["tampered_with_masks"] += 1
    return summary
