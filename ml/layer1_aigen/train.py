from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .augment import ScreenshotAugmentor
from .dataset import ImageRecordDataset, assign_splits, discover_samples, summarize_assignments
from .model import (
    CheckpointMetadata,
    EncoderConfig,
    HeadConfig,
    build_probe_head,
    load_open_clip_encoder,
    save_checkpoint,
    write_metadata_json,
)


def _require_torch():
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, Dataset

    return torch, nn, DataLoader, Dataset


class TorchImageDataset:
    def __init__(self, base: ImageRecordDataset, preprocess, augmentor: ScreenshotAugmentor | None):
        self.base = base
        self.preprocess = preprocess
        self.augmentor = augmentor

    def __len__(self):
        return len(self.base)

    def __getitem__(self, index):
        image, label, item = self.base[index]
        if self.augmentor is not None:
            image = self.augmentor(image)
        tensor = self.preprocess(image)
        return tensor, float(label), str(item.record.path)


def train(args: argparse.Namespace) -> dict:
    torch, nn, DataLoader, _ = _require_torch()

    heldout_generators = {g.strip().lower() for g in args.heldout_generators.split(",") if g.strip()}
    samples = discover_samples(args.data_root)
    if not samples:
        raise RuntimeError(
            "No training samples found. Expected real/ and generated/ image folders under --data-root."
        )
    assignments = assign_splits(
        samples,
        heldout_generators=heldout_generators,
        val_fraction=args.val_fraction,
        test_fraction=args.test_fraction,
    )
    summary = summarize_assignments(assignments)

    encoder_config = EncoderConfig(
        model_name=args.clip_model,
        pretrained=args.clip_pretrained,
        embedding_dim=args.embedding_dim,
        device=args.device,
    )
    head_config = HeadConfig(
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        use_mlp=not args.linear_probe,
    )
    encode, preprocess = load_open_clip_encoder(encoder_config)
    head = build_probe_head(encoder_config.embedding_dim, head_config).to(args.device)

    train_ds = TorchImageDataset(
        ImageRecordDataset(assignments, "train"), preprocess, ScreenshotAugmentor()
    )
    val_ds = TorchImageDataset(ImageRecordDataset(assignments, "val"), preprocess, None)
    if len(train_ds) == 0:
        raise RuntimeError("Training split is empty. Adjust the dataset or split fractions.")

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)

    optimizer = torch.optim.AdamW(head.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    criterion = nn.BCEWithLogitsLoss()

    def run_epoch(loader, training: bool):
        head.train(training)
        total_loss = 0.0
        total = 0
        correct = 0
        for images, labels, _paths in loader:
            images = images.to(args.device)
            labels = labels.to(args.device).unsqueeze(1)
            features = encode(images)
            logits = head(features)
            loss = criterion(logits, labels)
            if training:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
            total_loss += float(loss.item()) * len(labels)
            probs = torch.sigmoid(logits)
            predictions = (probs >= 0.5).float()
            correct += int((predictions == labels).sum().item())
            total += len(labels)
        return {
            "loss": total_loss / max(1, total),
            "accuracy": correct / max(1, total),
            "count": total,
        }

    history = []
    for epoch in range(1, args.epochs + 1):
        train_metrics = run_epoch(train_loader, training=True)
        val_metrics = run_epoch(val_loader, training=False) if len(val_ds) else {"loss": 0.0, "accuracy": 0.0, "count": 0}
        history.append({"epoch": epoch, "train": train_metrics, "val": val_metrics})
        print(
            json.dumps(
                {"epoch": epoch, "train": train_metrics, "val": val_metrics},
                separators=(",", ":"),
            )
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata = CheckpointMetadata(
        encoder=encoder_config,
        head=head_config,
        heldout_generators=sorted(heldout_generators),
        split_summary=summary,
        notes="Phase-0 L1 CLIP-head scaffold trained via frozen image encoder.",
    )
    save_checkpoint(output_dir / "l1_clip_head.pt", head_state_dict=head.state_dict(), metadata=metadata)
    write_metadata_json(output_dir / "l1_clip_head.metadata.json", metadata)
    (output_dir / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    return {"history": history, "summary": summary, "metadata": asdict(metadata)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the TruthPixel L1 CLIP-head scaffold.")
    parser.add_argument("--data-root", required=True, help="Dataset root with real/ and generated/ subfolders.")
    parser.add_argument("--output-dir", default="checkpoints/l1_aigen", help="Where to save the trained head.")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--clip-model", default="ViT-L-14")
    parser.add_argument("--clip-pretrained", default="openai")
    parser.add_argument("--embedding-dim", type=int, default=768)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--hidden-dim", type=int, default=512)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--linear-probe", action="store_true", help="Use a single linear layer instead of an MLP head.")
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--test-fraction", type=float, default=0.1)
    parser.add_argument(
        "--heldout-generators",
        default="midjourney,sdxl,flux",
        help="Comma-separated generated buckets that should go straight to test.",
    )
    return parser


if __name__ == "__main__":
    train(build_parser().parse_args())
