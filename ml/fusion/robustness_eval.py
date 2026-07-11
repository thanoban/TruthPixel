from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.analyzers import ALL_ANALYZERS
from app.config import get_settings
from app.fusion import fuse
from app.fusion.engine import _warned_learned_fusion_failures
from app.fusion.learned import load_learned_fusion_model
from app.schemas import ClaimContext
from app.signal_artifacts import INTERNAL_HEATMAP_BYTES_KEY

from ml.datagen.fraud_pairs import FraudPairRecord
from ml.layer1_aigen.augment import build_robustness_variants


def _read_manifest(path: Path) -> list[FraudPairRecord]:
    records: list[FraudPairRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(FraudPairRecord(**json.loads(line)))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid fraud-pair manifest row at line {line_number}: {exc}") from exc
    if not records:
        raise ValueError("Fraud-pair manifest is empty")
    return records


def _claim_context_from_record(record: FraudPairRecord) -> ClaimContext:
    return ClaimContext(
        order_id=record.example_id,
        product_sku=record.pair_kind,
        claim_reason="synthetic_fraud_pair" if record.label == 1 else "clean_claim_pair",
        listing_image_urls=[],
    )


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


def _precision_at_review_budget(
    probabilities: np.ndarray, labels: np.ndarray, *, review_budget_fraction: float
) -> float:
    if len(probabilities) == 0:
        return 0.0
    budget = max(1, int(np.ceil(len(probabilities) * review_budget_fraction)))
    top_indices = np.argsort(probabilities)[::-1][:budget]
    return float(np.mean(labels[top_indices]))


def _image_to_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


async def _run_signals(image_bytes: bytes, context: ClaimContext, claim_id: str):
    results = await asyncio.gather(
        *(analyzer().analyze(image_bytes, context, claim_id=claim_id) for analyzer in ALL_ANALYZERS)
    )
    return results


def _sanitize_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(evidence)
    cleaned.pop(INTERNAL_HEATMAP_BYTES_KEY, None)
    return cleaned


def _compute_variant_metrics(
    rows: list[dict[str, Any]],
    *,
    review_budget_fraction: float,
) -> dict[str, Any]:
    fused_scores = [float(row["fusion_risk_score"]) for row in rows]
    l2_scores = [float(row["l2_score"]) for row in rows]
    labels = [int(row["label"]) for row in rows]
    fused_predictions = [int(score >= 0.5) for score in fused_scores]
    l2_predictions = [int(score >= 0.5) for score in l2_scores]
    fused_review_flags = [bool(row["fusion_needs_review"]) for row in rows]
    return {
        "count": len(rows),
        "positives": sum(labels),
        "negatives": len(labels) - sum(labels),
        "fused_auroc": round(_roc_auc(fused_scores, labels), 6),
        "fused_accuracy": round(
            sum(int(pred == label) for pred, label in zip(fused_predictions, labels)) / len(labels),
            6,
        ),
        "fused_precision_at_review_budget": round(
            _precision_at_review_budget(
                np.asarray(fused_scores, dtype=np.float64),
                np.asarray(labels, dtype=np.int64),
                review_budget_fraction=review_budget_fraction,
            ),
            6,
        ),
        "fused_review_rate": round(sum(1 for flag in fused_review_flags if flag) / len(rows), 6),
        "l2_auroc": round(_roc_auc(l2_scores, labels), 6),
        "l2_accuracy": round(
            sum(int(pred == label) for pred, label in zip(l2_predictions, labels)) / len(labels),
            6,
        ),
        "mean_fused_score_positive": round(
            float(np.mean([score for score, label in zip(fused_scores, labels) if label == 1] or [0.0])),
            6,
        ),
        "mean_fused_score_negative": round(
            float(np.mean([score for score, label in zip(fused_scores, labels) if label == 0] or [0.0])),
            6,
        ),
        "mean_l2_score_positive": round(
            float(np.mean([score for score, label in zip(l2_scores, labels) if label == 1] or [0.0])),
            6,
        ),
        "mean_l2_score_negative": round(
            float(np.mean([score for score, label in zip(l2_scores, labels) if label == 0] or [0.0])),
            6,
        ),
    }


def _clear_runtime_caches() -> None:
    get_settings.cache_clear()
    load_learned_fusion_model.cache_clear()
    _warned_learned_fusion_failures.clear()


@contextmanager
def _override_fusion_model_path(path: str | None):
    original = os.environ.get("FUSION_MODEL_PATH")
    try:
        if path:
            os.environ["FUSION_MODEL_PATH"] = path
        else:
            os.environ.pop("FUSION_MODEL_PATH", None)
        _clear_runtime_caches()
        yield
    finally:
        if original is None:
            os.environ.pop("FUSION_MODEL_PATH", None)
        else:
            os.environ["FUSION_MODEL_PATH"] = original
        _clear_runtime_caches()


def evaluate_fraud_pairs(
    dataset_root: str | Path,
    manifest_path: str | Path,
    report_path: str | Path,
    *,
    fusion_model_path: str | None = None,
    review_budget_fraction: float = 0.1,
    limit: int | None = None,
) -> dict[str, Any]:
    dataset_root = Path(dataset_root)
    records = _read_manifest(Path(manifest_path))
    if limit is not None:
        records = records[:limit]

    by_variant: dict[str, list[dict[str, Any]]] = {
        "pristine": [],
        "jpeg_q75": [],
        "screenshot_sim": [],
        "social_roundtrip": [],
    }

    with _override_fusion_model_path(fusion_model_path):
        active_settings = get_settings()
        for record in records:
            claim_path = dataset_root / record.claim_image
            with Image.open(claim_path) as claim_image:
                variants = build_robustness_variants(claim_image.convert("RGB"))
            context = _claim_context_from_record(record)
            for variant_name, variant_image in variants.items():
                variant_bytes = _image_to_bytes(variant_image)
                claim_id = f"{record.example_id}-{variant_name}"
                signals = asyncio.run(_run_signals(variant_bytes, context, claim_id))
                fusion = fuse(signals, [])
                l2_signal = next(signal for signal in signals if signal.layer.value == "l2_forensics")
                by_variant[variant_name].append(
                    {
                        "claim_id": claim_id,
                        "label": record.label,
                        "pair_kind": record.pair_kind,
                        "variant": variant_name,
                        "fusion_risk_score": fusion.risk_score,
                        "fusion_needs_review": fusion.needs_review,
                        "fusion_version": fusion.fusion_version,
                        "l2_score": l2_signal.score if l2_signal.score is not None else 0.0,
                        "l2_confidence": l2_signal.confidence,
                        "l2_provider": l2_signal.evidence.get("provider"),
                        "l2_evidence": _sanitize_evidence(l2_signal.evidence),
                    }
                )

    report = {
        "dataset": "fraud_pairs",
        "dataset_root": str(dataset_root.resolve()),
        "manifest_path": str(Path(manifest_path).resolve()),
        "fusion_model_path": str(Path(fusion_model_path).resolve()) if fusion_model_path else None,
        "review_budget_fraction": review_budget_fraction,
        "active_fusion_mode": by_variant["pristine"][0]["fusion_version"] if by_variant["pristine"] else "unknown",
        "variants": {
            variant_name: {
                "metrics": _compute_variant_metrics(rows, review_budget_fraction=review_budget_fraction),
                "samples": rows,
            }
            for variant_name, rows in by_variant.items()
        },
        "notes": [
            "This robustness report is for A4 synthetic fraud-pair evaluation, not a published benchmark claim.",
            "Use a real CASIA v2 checkout plus the A1b harness for external splice-detection benchmarking.",
        ],
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate fused robustness on fraud-pair variants.")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--report-path", default="artifacts/fusion_robustness_report.json")
    parser.add_argument("--fusion-model-path")
    parser.add_argument("--review-budget-fraction", type=float, default=0.1)
    parser.add_argument("--limit", type=int)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    report = evaluate_fraud_pairs(
        args.dataset_root,
        args.manifest,
        args.report_path,
        fusion_model_path=args.fusion_model_path,
        review_budget_fraction=args.review_budget_fraction,
        limit=args.limit,
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
