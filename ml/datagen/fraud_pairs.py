from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True, slots=True)
class FraudPairRecord:
    example_id: str
    split: str
    label: int
    pair_kind: str
    source_image: str
    donor_image: str | None
    listing_image: str
    claim_image: str
    mask_image: str | None
    operations: list[str]
    synthetic_label_note: str


def _stable_fraction(value: str) -> float:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _iter_image_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            yield path


def discover_source_images(root: str | Path) -> list[Path]:
    return list(_iter_image_files(Path(root)))


def _assign_split(example_id: str, *, val_fraction: float, test_fraction: float) -> str:
    bucket = _stable_fraction(example_id)
    if bucket < val_fraction:
        return "val"
    if bucket < val_fraction + test_fraction:
        return "test"
    return "train"


def _open_rgb(path: Path, max_edge: int) -> Image.Image:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        return rgb.copy()


def _save_jpeg_roundtrip(image: Image.Image, quality: int) -> Image.Image:
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    with Image.open(buffer) as reopened:
        return reopened.convert("RGB").copy()


def _mild_claim_transform(image: Image.Image, rng: random.Random) -> tuple[Image.Image, list[str]]:
    transformed = image.copy()
    operations = ["source_real_photo"]
    if rng.random() < 0.8:
        quality = rng.randint(82, 95)
        transformed = _save_jpeg_roundtrip(transformed, quality)
        operations.append(f"jpeg_recompress_q{quality}")
    if rng.random() < 0.5:
        scale = rng.uniform(0.88, 1.0)
        new_size = (
            max(24, int(transformed.width * scale)),
            max(24, int(transformed.height * scale)),
        )
        transformed = transformed.resize(new_size, Image.Resampling.BICUBIC).resize(
            image.size,
            Image.Resampling.BICUBIC,
        )
        operations.append("resize_roundtrip")
    if rng.random() < 0.35:
        transformed = transformed.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.8)))
        operations.append("slight_blur")
    return transformed, operations


def _damage_patch(source: Image.Image, donor: Image.Image, rng: random.Random) -> tuple[Image.Image, Image.Image]:
    patch_width = max(32, min(source.width // 3, rng.randint(source.width // 6, source.width // 3)))
    patch_height = max(
        32,
        min(source.height // 3, rng.randint(source.height // 6, source.height // 3)),
    )
    donor_x = 0 if donor.width == patch_width else rng.randint(0, max(0, donor.width - patch_width))
    donor_y = 0 if donor.height == patch_height else rng.randint(0, max(0, donor.height - patch_height))
    patch = donor.crop((donor_x, donor_y, donor_x + patch_width, donor_y + patch_height)).convert("RGB")
    patch = ImageEnhance.Color(patch).enhance(rng.uniform(0.35, 0.75))
    patch = ImageEnhance.Contrast(patch).enhance(rng.uniform(1.2, 1.7))
    patch = _save_jpeg_roundtrip(patch, rng.randint(40, 70))

    # Add obviously synthetic "damage-like" streaks so the label stays honest.
    draw = ImageDraw.Draw(patch)
    for _ in range(rng.randint(3, 6)):
        x1 = rng.randint(0, patch.width - 1)
        y1 = rng.randint(0, patch.height - 1)
        x2 = rng.randint(0, patch.width - 1)
        y2 = rng.randint(0, patch.height - 1)
        color = (
            rng.randint(110, 180),
            rng.randint(15, 70),
            rng.randint(15, 70),
        )
        draw.line((x1, y1, x2, y2), fill=color, width=rng.randint(3, 8))
    for _ in range(rng.randint(1, 3)):
        x1 = rng.randint(0, patch.width - 10)
        y1 = rng.randint(0, patch.height - 10)
        x2 = min(patch.width - 1, x1 + rng.randint(10, patch.width // 2))
        y2 = min(patch.height - 1, y1 + rng.randint(10, patch.height // 2))
        draw.ellipse((x1, y1, x2, y2), fill=(95, 20, 20))

    mask = Image.new("L", patch.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    polygon = []
    for _ in range(rng.randint(5, 8)):
        polygon.append((rng.randint(0, patch.width - 1), rng.randint(0, patch.height - 1)))
    mask_draw.polygon(polygon, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=rng.uniform(1.2, 3.0)))
    return patch, mask


def _synthetic_fraud_transform(
    source: Image.Image,
    donor: Image.Image,
    rng: random.Random,
) -> tuple[Image.Image, Image.Image, list[str]]:
    base, operations = _mild_claim_transform(source, rng)
    patch, patch_mask = _damage_patch(source, donor, rng)
    mask_canvas = Image.new("L", base.size, 0)

    paste_x = 0 if base.width == patch.width else rng.randint(0, max(0, base.width - patch.width))
    paste_y = 0 if base.height == patch.height else rng.randint(0, max(0, base.height - patch.height))
    base.paste(patch, (paste_x, paste_y), patch_mask)
    mask_canvas.paste(patch_mask, (paste_x, paste_y))

    if rng.random() < 0.8:
        shadow = Image.new("RGB", base.size, (0, 0, 0))
        shadow_mask = mask_canvas.filter(ImageFilter.GaussianBlur(radius=rng.uniform(2.0, 4.5)))
        base = Image.composite(ImageChops.multiply(base, ImageEnhance.Brightness(shadow).enhance(0.0)), base, shadow_mask)
        operations.append("shadow_blend")

    base = _save_jpeg_roundtrip(base, rng.randint(55, 82))
    operations.extend(
        [
            "synthetic_splice_damage_patch",
            "mismatched_jpeg_history",
        ]
    )
    return base, mask_canvas, operations


def _write_image(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _record_to_json(record: FraudPairRecord) -> str:
    return json.dumps(asdict(record), sort_keys=True)


def generate_dataset(
    input_root: str | Path,
    output_root: str | Path,
    *,
    seed: int = 7,
    max_images: int | None = None,
    max_edge: int = 1024,
    val_fraction: float = 0.1,
    test_fraction: float = 0.2,
) -> dict[str, int]:
    source_images = discover_source_images(input_root)
    if not source_images:
        raise RuntimeError("No source images found under --input-root.")

    if max_images is not None:
        source_images = source_images[:max_images]

    output_root = Path(output_root)
    listing_dir = output_root / "listing"
    claim_dir = output_root / "claim"
    mask_dir = output_root / "mask"
    manifest_path = output_root / "manifest.jsonl"

    rng = random.Random(seed)
    records: list[FraudPairRecord] = []

    prepared_sources = [(path, _open_rgb(path, max_edge=max_edge)) for path in source_images]
    for index, (source_path, source_image) in enumerate(prepared_sources):
        donor_path, donor_image = prepared_sources[(index + 1) % len(prepared_sources)]

        listing_rel = Path("listing") / f"{index:04d}-listing.jpg"
        listing_path = output_root / listing_rel
        _write_image(listing_path, _save_jpeg_roundtrip(source_image, 92))

        legit_claim, legit_operations = _mild_claim_transform(source_image, rng)
        legit_rel = Path("claim") / f"{index:04d}-legit.jpg"
        _write_image(output_root / legit_rel, legit_claim)
        legit_id = f"pair-{index:04d}-legit"
        records.append(
            FraudPairRecord(
                example_id=legit_id,
                split=_assign_split(legit_id, val_fraction=val_fraction, test_fraction=test_fraction),
                label=0,
                pair_kind="clean_claim",
                source_image=str(source_path),
                donor_image=None,
                listing_image=str(listing_rel).replace("\\", "/"),
                claim_image=str(legit_rel).replace("\\", "/"),
                mask_image=None,
                operations=legit_operations,
                synthetic_label_note=(
                    "Label 0: real source image with only benign recompress/resize transforms."
                ),
            )
        )

        fraud_claim, fraud_mask, fraud_operations = _synthetic_fraud_transform(source_image, donor_image, rng)
        fraud_rel = Path("claim") / f"{index:04d}-fraud.jpg"
        fraud_mask_rel = Path("mask") / f"{index:04d}-fraud-mask.png"
        _write_image(output_root / fraud_rel, fraud_claim)
        _write_image(output_root / fraud_mask_rel, fraud_mask)
        fraud_id = f"pair-{index:04d}-fraud"
        records.append(
            FraudPairRecord(
                example_id=fraud_id,
                split=_assign_split(fraud_id, val_fraction=val_fraction, test_fraction=test_fraction),
                label=1,
                pair_kind="synthetic_splice",
                source_image=str(source_path),
                donor_image=str(donor_path),
                listing_image=str(listing_rel).replace("\\", "/"),
                claim_image=str(fraud_rel).replace("\\", "/"),
                mask_image=str(fraud_mask_rel).replace("\\", "/"),
                operations=fraud_operations,
                synthetic_label_note=(
                    "Label 1: synthetic fraud example created by compositing a low-quality donor "
                    "patch into a real source photo; use for calibration/training only."
                ),
            )
        )

    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        "\n".join(_record_to_json(record) for record in records) + "\n",
        encoding="utf-8",
    )
    summary = {
        "total_examples": len(records),
        "clean_examples": sum(1 for record in records if record.label == 0),
        "fraud_examples": sum(1 for record in records if record.label == 1),
        "source_images": len(prepared_sources),
    }
    (output_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic listing/claim fraud pairs.")
    parser.add_argument("--input-root", required=True, help="Directory of real source listing photos.")
    parser.add_argument("--output-root", required=True, help="Directory to write the generated dataset.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-images", type=int)
    parser.add_argument("--max-edge", type=int, default=1024)
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    result = generate_dataset(
        args.input_root,
        args.output_root,
        seed=args.seed,
        max_images=args.max_images,
        max_edge=args.max_edge,
        val_fraction=args.val_fraction,
        test_fraction=args.test_fraction,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
