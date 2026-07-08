"""Fusion engine — combines layer signals + agent findings into one risk score.

Phase 0: confidence-weighted average with per-layer base weights, plus the
screenshot-evasion combination rule. Phase 1 replaces this with a learned,
calibrated meta-classifier (stacking + Platt/isotonic + SHAP) trained on
labeled claims — same inputs/outputs, so it's a drop-in swap.

Must handle any signal being absent (layer error / agents skipped): fusion
degrades gracefully instead of failing. If a trained learned-fusion artifact is
configured, it is used as a drop-in replacement; otherwise the weighted fallback
remains the default.
"""

import os
from pathlib import Path

from ..config import get_settings
from .learned import load_learned_fusion_model
from ..schemas import AgentFinding, FusionResult, Layer, SignalResult

# Base weights encode prior trust per layer. L4 metadata is deliberately low:
# absent/clean metadata is neutral evidence, never proof.
BASE_WEIGHTS: dict[str, float] = {
    Layer.L1_AIGEN.value: 1.0,
    Layer.L2_FORENSICS.value: 1.0,
    Layer.L3_RECAPTURE.value: 0.9,
    Layer.L4_METADATA.value: 0.4,
    Layer.L5_CONTEXT.value: 1.0,
    "semantic_inspector": 0.8,
    "damage_plausibility": 0.8,
}

RECAPTURE_COMBO_BOOST = 0.15


def _weighted_fuse(signals: list[SignalResult], agents: list[AgentFinding]) -> FusionResult:
    inputs: list[tuple[str, float, float]] = [
        (s.layer.value, s.score, s.confidence)
        for s in signals
        if s.score is not None and s.error is None
    ]
    inputs += [(a.agent, a.score, a.confidence) for a in agents if a.score is not None]

    weighted = [
        (name, score, BASE_WEIGHTS.get(name, 0.5) * confidence)
        for name, score, confidence in inputs
    ]
    total = sum(w for _, _, w in weighted)
    if total <= 0:
        # No usable signal at all — force human review, never silently pass.
        return FusionResult(
            risk_score=0.5,
            needs_review=True,
            contributions={},
            fusion_version="weighted-avg-0.1",
        )

    risk = sum(score * w for _, score, w in weighted) / total

    # Screenshot-evasion rule: recapture detected AND (metadata absent OR semantic
    # artifacts present) is more suspicious than the weighted average captures.
    by_name = {name: score for name, score, _ in inputs}
    recapture = by_name.get(Layer.L3_RECAPTURE.value, 0.0) or 0.0
    metadata_absent = not any(
        s.layer == Layer.L4_METADATA and s.evidence.get("exif_present") for s in signals
    )
    semantic = by_name.get("semantic_inspector", 0.0) or 0.0
    if recapture >= 0.7 and (metadata_absent or semantic >= 0.6):
        risk = min(1.0, risk + RECAPTURE_COMBO_BOOST)

    contributions = {
        name: round(score * w / total, 4) for (name, score, w) in weighted if w > 0
    }
    return FusionResult(
        risk_score=round(risk, 4),
        needs_review=False,
        contributions=contributions,
        fusion_version="weighted-avg-0.1",
    )


def fuse(signals: list[SignalResult], agents: list[AgentFinding]) -> FusionResult:
    settings = get_settings()
    learned_path = os.getenv("FUSION_MODEL_PATH", "").strip()
    if learned_path:
        try:
            model = load_learned_fusion_model(str(Path(learned_path).expanduser().resolve()))
            return model.score(signals, agents, settings.review_threshold)
        except Exception:
            pass

    result = _weighted_fuse(signals, agents)
    result.needs_review = result.risk_score >= settings.review_threshold
    return result
