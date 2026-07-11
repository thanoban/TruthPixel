import json
from pathlib import Path

from ml.fusion.features import FEATURE_NAMES
from ml.fusion.train_meta import ARTIFACT_SCHEMA_VERSION, RUNTIME_LOADER, train_and_export


def _example(claim_id: str, label: int, recapture: float, semantic: float, metadata_absent: bool) -> dict:
    return {
        "claim_id": claim_id,
        "label": label,
        "signals": [
            {"layer": "l1_aigen", "score": 0.2 + (0.5 * label), "confidence": 0.8},
            {"layer": "l2_forensics", "score": 0.1 + (0.6 * label), "confidence": 0.7},
            {"layer": "l3_recapture", "score": recapture, "confidence": 0.9},
            {
                "layer": "l4_metadata",
                "score": 0.4 if metadata_absent else 0.1,
                "confidence": 0.3,
                "evidence": {"exif_present": not metadata_absent},
            },
            {"layer": "l5_context", "score": 0.2 + (0.4 * label), "confidence": 0.75},
        ],
        "agent_findings": [
            {"agent": "semantic_inspector", "score": semantic, "confidence": 0.8},
            {"agent": "damage_plausibility", "score": 0.2 + (0.4 * label), "confidence": 0.7},
        ],
    }


def test_train_and_export_writes_backend_friendly_artifacts(tmp_path: Path):
    input_path = tmp_path / "fusion_train.jsonl"
    output_dir = tmp_path / "artifacts"
    records = [
        _example("c1", 0, 0.1, 0.2, False),
        _example("c2", 0, 0.15, 0.3, False),
        _example("c3", 0, 0.2, 0.25, False),
        _example("c4", 1, 0.8, 0.7, True),
        _example("c5", 1, 0.75, 0.8, True),
        _example("c6", 1, 0.9, 0.65, True),
    ]
    input_path.write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )

    manifest = train_and_export(input_path, output_dir, shap_background_size=4)

    assert manifest["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert manifest["model_name"] == "learned-fusion-logreg-v1"
    assert manifest["model"] == "model.json"
    assert manifest["runtime_entrypoint"] == RUNTIME_LOADER
    assert manifest["feature_count"] == len(FEATURE_NAMES)
    assert (output_dir / "model.json").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "feature_table.csv").exists()
    assert (output_dir / "calibration.csv").exists()
    assert (output_dir / "shap_background.csv").exists()

    model_payload = json.loads((output_dir / "model.json").read_text(encoding="utf-8"))
    assert model_payload["artifact_schema_version"] == ARTIFACT_SCHEMA_VERSION
    assert model_payload["model_name"] == "learned-fusion-logreg-v1"
    assert len(model_payload["feature_names"]) == len(model_payload["coefficients"])
    assert model_payload["runtime_expectations"]["loader"] == RUNTIME_LOADER
    assert (
        model_payload["runtime_expectations"]["supported_schema_version"]
        == ARTIFACT_SCHEMA_VERSION
    )
    assert model_payload["metrics"]["train_rows"] >= 4
    assert "ece_calibrated" in model_payload["metrics"]
    assert "precision_at_review_budget_calibrated" in model_payload["metrics"]
