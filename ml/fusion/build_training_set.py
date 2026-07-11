from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.analyzers import ALL_ANALYZERS
from app.schemas import AgentFinding, ClaimContext
from app.signal_artifacts import INTERNAL_HEATMAP_BYTES_KEY

from ml.datagen.fraud_pairs import FraudPairRecord


def _read_manifest(path: Path) -> list[FraudPairRecord]:
    records: list[FraudPairRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                records.append(FraudPairRecord(**payload))
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"Invalid fraud-pair manifest row at line {line_number}: {exc}") from exc
    if not records:
        raise ValueError("Fraud-pair manifest is empty")
    return records


async def _run_signals(image_bytes: bytes, context: ClaimContext, claim_id: str) -> list[dict[str, Any]]:
    results = await asyncio.gather(
        *(analyzer().analyze(image_bytes, context, claim_id=claim_id) for analyzer in ALL_ANALYZERS)
    )
    serialized: list[dict[str, Any]] = []
    for result in results:
        evidence = dict(result.evidence)
        evidence.pop(INTERNAL_HEATMAP_BYTES_KEY, None)
        serialized.append(result.model_copy(update={"evidence": evidence}).model_dump(mode="json"))
    return serialized


def _claim_context_from_record(record: FraudPairRecord) -> ClaimContext:
    return ClaimContext(
        order_id=record.example_id,
        product_sku=record.pair_kind,
        claim_reason="synthetic_fraud_pair" if record.label == 1 else "clean_claim_pair",
        listing_image_urls=[],
    )


def build_training_examples(
    dataset_root: str | Path,
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    include_agent_findings: bool = False,
    limit: int | None = None,
) -> dict[str, int]:
    dataset_root = Path(dataset_root)
    manifest_rows = _read_manifest(Path(manifest_path))
    if limit is not None:
        manifest_rows = manifest_rows[:limit]

    examples: list[dict[str, Any]] = []
    for record in manifest_rows:
        claim_path = dataset_root / record.claim_image
        if not claim_path.is_file():
            raise FileNotFoundError(f"Missing claim image for {record.example_id}: {claim_path}")
        image_bytes = claim_path.read_bytes()
        context = _claim_context_from_record(record)
        signals = asyncio.run(_run_signals(image_bytes, context, record.example_id))
        agent_findings: list[dict[str, Any]]
        if include_agent_findings:
            # The first production artifact should stay CPU/local-friendly by default; this
            # hook exists so a later run can opt into real Vertex-backed findings.
            agent_findings = []
        else:
            agent_findings = []

        examples.append(
            {
                "claim_id": record.example_id,
                "label": record.label,
                "signals": signals,
                "agent_findings": agent_findings,
                "source": {
                    "dataset_split": record.split,
                    "pair_kind": record.pair_kind,
                    "listing_image": record.listing_image,
                    "claim_image": record.claim_image,
                    "mask_image": record.mask_image,
                    "operations": record.operations,
                    "synthetic_label_note": record.synthetic_label_note,
                },
            }
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "\n".join(json.dumps(example, sort_keys=True) for example in examples) + "\n",
        encoding="utf-8",
    )
    return {
        "rows": len(examples),
        "positives": sum(1 for row in examples if int(row["label"]) == 1),
        "negatives": sum(1 for row in examples if int(row["label"]) == 0),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build learned-fusion training JSONL from a fraud-pairs manifest."
    )
    parser.add_argument("--dataset-root", required=True, help="Root directory of the generated fraud-pairs dataset.")
    parser.add_argument("--manifest", required=True, help="Path to fraud-pairs manifest.jsonl.")
    parser.add_argument("--output", required=True, help="Where to write the learned-fusion training JSONL.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--include-agent-findings", action="store_true")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    summary = build_training_examples(
        args.dataset_root,
        args.manifest,
        args.output,
        include_agent_findings=args.include_agent_findings,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
