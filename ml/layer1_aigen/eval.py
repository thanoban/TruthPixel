from __future__ import annotations

import argparse
import json
from pathlib import Path

from .augment import build_robustness_variants
from .dataset import ImageRecordDataset, assign_splits, discover_samples
from .model import load_open_clip_encoder


def _require_torch():
    import torch

    return torch


def _roc_auc(scores: list[float], labels: list[int]) -> float:
    positives = [(score, label) for score, label in zip(scores, labels) if label == 1]
    negatives = [(score, label) for score, label in zip(scores, labels) if label == 0]
    if not positives or not negatives:
        return 0.0
    wins = 0.0
    ties = 0.0
    for pos_score, _ in positives:
        for neg_score, _ in negatives:
            if pos_score > neg_score:
                wins += 1.0
            elif pos_score == neg_score:
                ties += 1.0
    return (wins + 0.5 * ties) / (len(positives) * len(negatives))


def evaluate(args: argparse.Namespace) -> dict:
    torch = _require_torch()
    checkpoint = torch.load(args.checkpoint, map_location=args.device, weights_only=False)
    metadata = checkpoint["metadata"]
    heldout_generators = {
        g.strip().lower() for g in args.heldout_generators.split(",") if g.strip()
    }
    samples = discover_samples(args.data_root)
    if not samples:
        raise RuntimeError(
            "No evaluation samples found. Expected real/ and generated/ image folders under --data-root."
        )
    assignments = assign_splits(
        samples,
        heldout_generators=heldout_generators,
        val_fraction=args.val_fraction,
        test_fraction=args.test_fraction,
    )

    encoder_cfg = metadata["encoder"]
    encode, preprocess = load_open_clip_encoder(
        type("EncoderConfigProxy", (), encoder_cfg)()
    )
    head_config = metadata["head"]
    from .model import build_probe_head

    head = build_probe_head(encoder_cfg["embedding_dim"], type("HeadConfigProxy", (), head_config)())
    head.load_state_dict(checkpoint["head_state_dict"])
    head.to(args.device)
    head.eval()

    test_set = ImageRecordDataset(assignments, "test")
    if len(test_set) == 0:
        raise RuntimeError(
            "Test split is empty. Add heldout generators or increase --test-fraction."
        )
    metrics_by_variant: dict[str, dict[str, float]] = {}
    for variant_name in ("pristine", "jpeg_q75", "screenshot_sim", "social_roundtrip"):
        scores: list[float] = []
        labels: list[int] = []
        for image, label, _item in test_set:
            variant_image = build_robustness_variants(image)[variant_name]
            tensor = preprocess(variant_image).unsqueeze(0).to(args.device)
            with torch.no_grad():
                features = encode(tensor)
                logits = head(features)
                score = float(torch.sigmoid(logits).item())
            scores.append(score)
            labels.append(label)
        accuracy = 0.0
        if labels:
            accuracy = sum(
                int((score >= 0.5) == bool(label)) for score, label in zip(scores, labels)
            ) / len(labels)
        metrics_by_variant[variant_name] = {
            "count": len(labels),
            "accuracy": round(accuracy, 4),
            "auroc": round(_roc_auc(scores, labels), 4),
        }

    output = {
        "checkpoint": args.checkpoint,
        "heldout_generators": sorted(heldout_generators),
        "metrics": metrics_by_variant,
    }
    Path(args.report_path).write_text(json.dumps(output, indent=2), encoding="utf-8")
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate the TruthPixel L1 scaffold.")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--report-path", default="checkpoints/l1_aigen/eval_report.json")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--test-fraction", type=float, default=0.1)
    parser.add_argument("--heldout-generators", default="midjourney,sdxl,flux")
    return parser


if __name__ == "__main__":
    result = evaluate(build_parser().parse_args())
    print(json.dumps(result, indent=2))
