"""Train a learned fusion meta-classifier and export backend-friendly artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split

from .features import FEATURE_NAMES, extract_feature_row, row_to_vector

ARTIFACT_SCHEMA_VERSION = "learned-fusion/v1"
RUNTIME_LOADER = "backend.app.fusion.learned:LearnedFusionModel"


def _sigmoid(value: np.ndarray | float) -> np.ndarray | float:
    clipped = np.clip(value, -60.0, 60.0)
    return 1.0 / (1.0 + np.exp(-clipped))


def load_examples(path: Path) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            if "label" not in record:
                raise ValueError(f"Line {line_number} is missing a 'label' field")
            examples.append(record)
    if len(examples) < 4:
        raise ValueError("Need at least 4 labeled examples to train learned fusion")
    labels = {int(example["label"]) for example in examples}
    if labels != {0, 1}:
        raise ValueError("Training data must contain both negative and positive labels")
    return examples


def _split_indices(
    labels: np.ndarray,
    calibration_fraction: float,
    random_state: int,
) -> tuple[np.ndarray, np.ndarray]:
    indices = np.arange(len(labels))
    label_counts = np.bincount(labels, minlength=2)
    if calibration_fraction <= 0 or len(labels) < 6 or label_counts.min() < 2:
        return indices, indices
    train_idx, calibration_idx = train_test_split(
        indices,
        test_size=calibration_fraction,
        stratify=labels,
        random_state=random_state,
    )
    return np.asarray(train_idx), np.asarray(calibration_idx)


def _build_background_rows(
    rows: list[dict[str, Any]],
    labels: np.ndarray,
    max_rows: int,
    random_state: int,
) -> list[dict[str, Any]]:
    if len(rows) <= max_rows:
        return rows
    rng = random.Random(random_state)
    positives = [row for row, label in zip(rows, labels, strict=True) if int(label) == 1]
    negatives = [row for row, label in zip(rows, labels, strict=True) if int(label) == 0]
    rng.shuffle(positives)
    rng.shuffle(negatives)
    take_pos = min(len(positives), max_rows // 2)
    take_neg = min(len(negatives), max_rows - take_pos)
    selected = positives[:take_pos] + negatives[:take_neg]
    while len(selected) < max_rows:
        pool = positives[take_pos:] + negatives[take_neg:]
        if not pool:
            break
        selected.append(pool.pop(0))
    return selected


def train_and_export(
    input_path: Path,
    output_dir: Path,
    *,
    model_name: str = "learned-fusion-logreg-v1",
    calibration_fraction: float = 0.3,
    random_state: int = 7,
    shap_background_size: int = 128,
) -> dict[str, Any]:
    examples = load_examples(input_path)
    feature_rows = [
        extract_feature_row(example.get("signals", []), example.get("agent_findings", []))
        for example in examples
    ]
    feature_matrix = np.asarray(
        [row_to_vector(row, FEATURE_NAMES) for row in feature_rows],
        dtype=np.float64,
    )
    labels = np.asarray([int(example["label"]) for example in examples], dtype=np.int64)
    claim_ids = [str(example.get("claim_id", f"example-{index}")) for index, example in enumerate(examples)]

    means = feature_matrix.mean(axis=0)
    scales = feature_matrix.std(axis=0)
    scales[scales == 0] = 1.0
    standardized = (feature_matrix - means) / scales

    train_idx, calibration_idx = _split_indices(labels, calibration_fraction, random_state)
    base_model = LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        random_state=random_state,
    )
    base_model.fit(standardized[train_idx], labels[train_idx])

    raw_logits = standardized @ base_model.coef_[0] + float(base_model.intercept_[0])
    raw_probabilities = _sigmoid(raw_logits)

    calibrator = LogisticRegression(max_iter=1000, random_state=random_state)
    calibrator.fit(raw_logits[calibration_idx].reshape(-1, 1), labels[calibration_idx])
    calibrated_probabilities = calibrator.predict_proba(raw_logits.reshape(-1, 1))[:, 1]

    metrics = {
        "train_rows": int(len(train_idx)),
        "calibration_rows": int(len(calibration_idx)),
        "auroc_raw": round(float(roc_auc_score(labels, raw_probabilities)), 6),
        "auroc_calibrated": round(float(roc_auc_score(labels, calibrated_probabilities)), 6),
        "brier_raw": round(float(brier_score_loss(labels, raw_probabilities)), 6),
        "brier_calibrated": round(float(brier_score_loss(labels, calibrated_probabilities)), 6),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "model.json"
    feature_table_path = output_dir / "feature_table.csv"
    calibration_path = output_dir / "calibration.csv"
    shap_background_path = output_dir / "shap_background.csv"
    manifest_path = output_dir / "manifest.json"

    exported_model = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "model_type": "logistic_regression",
        "model_name": model_name,
        "feature_names": list(FEATURE_NAMES),
        "feature_means": means.tolist(),
        "feature_scales": scales.tolist(),
        "coefficients": base_model.coef_[0].tolist(),
        "intercept": float(base_model.intercept_[0]),
        "calibration": {
            "method": "platt",
            "coefficient": float(calibrator.coef_[0][0]),
            "intercept": float(calibrator.intercept_[0]),
        },
        "runtime_expectations": {
            "loader": RUNTIME_LOADER,
            "feature_layout": "ml.fusion.features.FEATURE_NAMES",
            "supported_schema_version": ARTIFACT_SCHEMA_VERSION,
            "supported_calibration_method": "platt",
            "expects_review_threshold_from_runtime": True,
        },
        "metrics": metrics,
    }
    model_path.write_text(json.dumps(exported_model, indent=2), encoding="utf-8")

    with feature_table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["claim_id", "label", "split", *FEATURE_NAMES],
        )
        writer.writeheader()
        for idx, row in enumerate(feature_rows):
            split = "calibration" if idx in set(calibration_idx.tolist()) else "train"
            writer.writerow(
                {
                    "claim_id": claim_ids[idx],
                    "label": int(labels[idx]),
                    "split": split,
                    **{name: row[name] for name in FEATURE_NAMES},
                }
            )

    with calibration_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "claim_id",
                "label",
                "split",
                "raw_logit",
                "raw_probability",
                "calibrated_probability",
            ],
        )
        writer.writeheader()
        calibration_index_set = set(calibration_idx.tolist())
        for idx, claim_id in enumerate(claim_ids):
            writer.writerow(
                {
                    "claim_id": claim_id,
                    "label": int(labels[idx]),
                    "split": "calibration" if idx in calibration_index_set else "train",
                    "raw_logit": round(float(raw_logits[idx]), 6),
                    "raw_probability": round(float(raw_probabilities[idx]), 6),
                    "calibrated_probability": round(float(calibrated_probabilities[idx]), 6),
                }
            )

    background_rows = _build_background_rows(
        [
            {
                "claim_id": claim_ids[idx],
                "label": int(labels[idx]),
                **{name: feature_rows[idx][name] for name in FEATURE_NAMES},
            }
            for idx in range(len(feature_rows))
        ],
        labels,
        shap_background_size,
        random_state,
    )
    with shap_background_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["claim_id", "label", *FEATURE_NAMES],
        )
        writer.writeheader()
        writer.writerows(background_rows)

    manifest = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "model_name": model_name,
        "model": model_path.name,
        "feature_table": feature_table_path.name,
        "calibration_table": calibration_path.name,
        "shap_background": shap_background_path.name,
        "runtime_entrypoint": RUNTIME_LOADER,
        "feature_count": len(FEATURE_NAMES),
        "required_runtime_files": [model_path.name],
        "metrics": metrics,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="JSONL file of labeled claims")
    parser.add_argument("--output-dir", type=Path, required=True, help="Artifact output directory")
    parser.add_argument("--model-name", default="learned-fusion-logreg-v1")
    parser.add_argument("--calibration-fraction", type=float, default=0.3)
    parser.add_argument("--random-state", type=int, default=7)
    parser.add_argument("--shap-background-size", type=int, default=128)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    train_and_export(
        args.input,
        args.output_dir,
        model_name=args.model_name,
        calibration_fraction=args.calibration_fraction,
        random_state=args.random_state,
        shap_background_size=args.shap_background_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
