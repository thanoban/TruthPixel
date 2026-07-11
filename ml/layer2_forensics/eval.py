from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from backend.app.forensics_classic import run_classic_forensics

from .dataset import AssignedCasiaSample, assign_splits, discover_casia_v2_samples, summarize_assignments


@dataclass(frozen=True, slots=True)
class LocalizationMetrics:
    intersection_over_union: float
    f1: float
    precision: float
    recall: float


def _roc_auc(scores: list[float], labels: list[int]) -> float:
    positives = [score for score, label in zip(scores, labels) if label == 1]
    negatives = [score for score, label in zip(scores, labels) if label == 0]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    ties = 0.0
    for pos_score in positives:
        for neg_score in negatives:
            if pos_score > neg_score:
                wins += 1.0
            elif pos_score == neg_score:
                ties += 1.0
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


def _resize_probability_map(block_map: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray((np.clip(block_map, 0.0, 1.0) * 255).astype(np.uint8), mode="L")
    resized = image.resize(size, Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32) / 255.0


def _load_binary_mask(mask_path: Path, size: tuple[int, int]) -> np.ndarray:
    with Image.open(mask_path) as image:
        mask = image.convert("L")
        if mask.size != size:
            mask = mask.resize(size, Image.Resampling.NEAREST)
        array = np.asarray(mask, dtype=np.uint8)
    return array >= 127


def _localization_metrics(
    probability_map: np.ndarray, mask: np.ndarray, *, threshold: float
) -> LocalizationMetrics:
    prediction = probability_map >= threshold
    intersection = int(np.logical_and(prediction, mask).sum())
    union = int(np.logical_or(prediction, mask).sum())
    predicted = int(prediction.sum())
    actual = int(mask.sum())
    precision = intersection / predicted if predicted else 0.0
    recall = intersection / actual if actual else 0.0
    if precision + recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    iou = intersection / union if union else 0.0
    return LocalizationMetrics(
        intersection_over_union=round(iou, 4),
        f1=round(f1, 4),
        precision=round(precision, 4),
        recall=round(recall, 4),
    )


def _evaluate_assignments(
    assignments: list[AssignedCasiaSample],
    *,
    split: str,
    localization_threshold: float,
) -> dict:
    selected = [item for item in assignments if item.split == split]
    if not selected:
        raise RuntimeError(f"Split '{split}' is empty. Adjust the fractions or add more data.")

    scores: list[float] = []
    labels: list[int] = []
    localization_rows: list[LocalizationMetrics] = []
    skipped_missing_masks = 0
    per_sample: list[dict[str, object]] = []

    for item in selected:
        image_bytes = item.sample.image_path.read_bytes()
        result = run_classic_forensics(image_bytes)
        scores.append(result.score)
        labels.append(item.sample.label)

        row: dict[str, object] = {
            "sample_id": item.sample.sample_id,
            "label": item.sample.label,
            "score": result.score,
            "confidence": result.confidence,
            "image_path": str(item.sample.image_path),
        }
        if item.sample.label == 1:
            row["has_mask"] = item.sample.mask_path is not None
            if item.sample.mask_path is not None:
                probability_map = _resize_probability_map(result.anomaly_map, result.image_size)
                mask = _load_binary_mask(item.sample.mask_path, result.image_size)
                metrics = _localization_metrics(
                    probability_map,
                    mask,
                    threshold=localization_threshold,
                )
                localization_rows.append(metrics)
                row["localization"] = {
                    "iou": metrics.intersection_over_union,
                    "f1": metrics.f1,
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                }
            else:
                skipped_missing_masks += 1
        per_sample.append(row)

    accuracy = sum(int((score >= 0.5) == bool(label)) for score, label in zip(scores, labels)) / len(labels)
    localization_summary = {
        "count": len(localization_rows),
        "skipped_missing_masks": skipped_missing_masks,
        "mean_iou": round(
            float(np.mean([row.intersection_over_union for row in localization_rows])), 4
        )
        if localization_rows
        else 0.0,
        "mean_f1": round(float(np.mean([row.f1 for row in localization_rows])), 4)
        if localization_rows
        else 0.0,
        "mean_precision": round(float(np.mean([row.precision for row in localization_rows])), 4)
        if localization_rows
        else 0.0,
        "mean_recall": round(float(np.mean([row.recall for row in localization_rows])), 4)
        if localization_rows
        else 0.0,
        "threshold": localization_threshold,
    }
    return {
        "split": split,
        "count": len(labels),
        "authentic_count": sum(1 for label in labels if label == 0),
        "tampered_count": sum(1 for label in labels if label == 1),
        "accuracy": round(accuracy, 4),
        "auroc": round(_roc_auc(scores, labels), 4),
        "localization": localization_summary,
        "samples": per_sample,
    }


def evaluate(args: argparse.Namespace) -> dict:
    samples = discover_casia_v2_samples(args.data_root)
    if not samples:
        raise RuntimeError("No CASIA samples found under --data-root.")
    assignments = assign_splits(
        samples,
        val_fraction=args.val_fraction,
        test_fraction=args.test_fraction,
    )
    report = {
        "dataset": "CASIA v2",
        "data_root": str(Path(args.data_root).resolve()),
        "split_summary": summarize_assignments(assignments),
        "evaluation": _evaluate_assignments(
            assignments,
            split=args.eval_split,
            localization_threshold=args.localization_threshold,
        ),
        "notes": [
            "No benchmark claim should be published until this report is generated on a real CASIA v2 checkout.",
            "Use corrected ground-truth masks when available; some widely shared CASIA masks have rotation and size issues.",
        ],
    }
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate TruthPixel classical L2 on CASIA v2.")
    parser.add_argument("--data-root", required=True, help="CASIA v2 root containing Au/, Tp/, and Gt/.")
    parser.add_argument("--report-path", default="artifacts/casia_v2_classical_eval.json")
    parser.add_argument("--eval-split", default="test", choices=("train", "val", "test"))
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--localization-threshold", type=float, default=0.5)
    return parser


if __name__ == "__main__":
    result = evaluate(build_parser().parse_args())
    print(json.dumps(result, indent=2))
