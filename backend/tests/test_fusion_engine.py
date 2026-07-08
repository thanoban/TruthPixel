import json
from pathlib import Path

from app.config import get_settings
from app.fusion import fuse
from app.fusion.learned import load_learned_fusion_model
from app.schemas import AgentFinding, Layer, SignalResult
from ml.fusion.train_meta import train_and_export


def _write_training_data(path: Path):
    records = [
        {
            "claim_id": "neg-1",
            "label": 0,
            "signals": [
                {"layer": "l1_aigen", "score": 0.15, "confidence": 0.8},
                {"layer": "l2_forensics", "score": 0.2, "confidence": 0.75},
                {"layer": "l3_recapture", "score": 0.1, "confidence": 0.8},
                {"layer": "l4_metadata", "score": 0.1, "confidence": 0.2, "evidence": {"exif_present": True}},
                {"layer": "l5_context", "score": 0.2, "confidence": 0.75},
            ],
            "agent_findings": [
                {"agent": "semantic_inspector", "score": 0.2, "confidence": 0.8},
                {"agent": "damage_plausibility", "score": 0.25, "confidence": 0.7},
            ],
        },
        {
            "claim_id": "neg-2",
            "label": 0,
            "signals": [
                {"layer": "l1_aigen", "score": 0.2, "confidence": 0.85},
                {"layer": "l2_forensics", "score": 0.15, "confidence": 0.7},
                {"layer": "l3_recapture", "score": 0.18, "confidence": 0.8},
                {"layer": "l4_metadata", "score": 0.12, "confidence": 0.2, "evidence": {"exif_present": True}},
                {"layer": "l5_context", "score": 0.18, "confidence": 0.7},
            ],
            "agent_findings": [
                {"agent": "semantic_inspector", "score": 0.28, "confidence": 0.75},
                {"agent": "damage_plausibility", "score": 0.2, "confidence": 0.7},
            ],
        },
        {
            "claim_id": "pos-1",
            "label": 1,
            "signals": [
                {"layer": "l1_aigen", "score": 0.75, "confidence": 0.9},
                {"layer": "l2_forensics", "score": 0.8, "confidence": 0.85},
                {"layer": "l3_recapture", "score": 0.82, "confidence": 0.9},
                {"layer": "l4_metadata", "score": 0.45, "confidence": 0.3, "evidence": {"exif_present": False}},
                {"layer": "l5_context", "score": 0.78, "confidence": 0.8},
            ],
            "agent_findings": [
                {"agent": "semantic_inspector", "score": 0.74, "confidence": 0.8},
                {"agent": "damage_plausibility", "score": 0.7, "confidence": 0.8},
            ],
        },
        {
            "claim_id": "pos-2",
            "label": 1,
            "signals": [
                {"layer": "l1_aigen", "score": 0.8, "confidence": 0.88},
                {"layer": "l2_forensics", "score": 0.78, "confidence": 0.8},
                {"layer": "l3_recapture", "score": 0.9, "confidence": 0.92},
                {"layer": "l4_metadata", "score": 0.5, "confidence": 0.25, "evidence": {"exif_present": False}},
                {"layer": "l5_context", "score": 0.82, "confidence": 0.8},
            ],
            "agent_findings": [
                {"agent": "semantic_inspector", "score": 0.79, "confidence": 0.78},
                {"agent": "damage_plausibility", "score": 0.76, "confidence": 0.82},
            ],
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_fuse_uses_learned_model_when_configured(tmp_path: Path, monkeypatch):
    input_path = tmp_path / "train.jsonl"
    model_dir = tmp_path / "fusion_model"
    _write_training_data(input_path)
    train_and_export(input_path, model_dir, calibration_fraction=0.5)

    monkeypatch.setenv("FUSION_MODEL_PATH", (model_dir / "model.json").as_posix())
    get_settings.cache_clear()
    load_learned_fusion_model.cache_clear()
    try:
        result = fuse(
            [
                SignalResult(layer=Layer.L1_AIGEN, score=0.78, confidence=0.9),
                SignalResult(layer=Layer.L2_FORENSICS, score=0.76, confidence=0.82),
                SignalResult(layer=Layer.L3_RECAPTURE, score=0.88, confidence=0.9),
                SignalResult(
                    layer=Layer.L4_METADATA,
                    score=0.45,
                    confidence=0.2,
                    evidence={"exif_present": False},
                ),
                SignalResult(layer=Layer.L5_CONTEXT, score=0.8, confidence=0.8),
            ],
            [
                AgentFinding(agent="semantic_inspector", score=0.77, confidence=0.8),
                AgentFinding(agent="damage_plausibility", score=0.72, confidence=0.8),
            ],
        )
    finally:
        get_settings.cache_clear()
        load_learned_fusion_model.cache_clear()

    assert result.fusion_version == "learned-fusion-logreg-v1"
    assert result.risk_score > 0.5
    assert "l3_recapture" in result.contributions


def test_fuse_falls_back_to_weighted_average_when_model_missing(monkeypatch):
    monkeypatch.setenv("FUSION_MODEL_PATH", "missing/model.json")
    get_settings.cache_clear()
    load_learned_fusion_model.cache_clear()
    try:
        result = fuse([SignalResult(layer=Layer.L1_AIGEN, score=0.8, confidence=0.9)], [])
    finally:
        get_settings.cache_clear()
        load_learned_fusion_model.cache_clear()

    assert result.fusion_version == "weighted-avg-0.1"
