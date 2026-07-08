"""Feature assembly for learned fusion.

The layout mirrors backend signal/agent contracts but stays light enough to be
used from both ML training code and backend inference without sklearn.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

LAYER_NAMES: tuple[str, ...] = (
    "l1_aigen",
    "l2_forensics",
    "l3_recapture",
    "l4_metadata",
    "l5_context",
)
AGENT_NAMES: tuple[str, ...] = ("semantic_inspector", "damage_plausibility")
SOURCE_NAMES: tuple[str, ...] = LAYER_NAMES + AGENT_NAMES + ("fusion_context",)


def _feature_names_for_sources(sources: Sequence[str]) -> list[str]:
    names: list[str] = []
    for source in sources:
        if source == "fusion_context":
            continue
        names.extend(
            (
                f"{source}_score",
                f"{source}_confidence",
                f"{source}_available",
            )
        )
    names.extend(
        (
            "metadata_absent",
            "recapture_x_metadata_absent",
            "recapture_flag",
            "semantic_flag",
            "available_signal_count",
            "available_agent_count",
        )
    )
    return names


FEATURE_NAMES: tuple[str, ...] = tuple(_feature_names_for_sources(SOURCE_NAMES))


def _get_field(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(field, default)
    return getattr(item, field, default)


def _normalize_key(value: Any) -> str:
    if value is None:
        return ""
    return getattr(value, "value", value)


def _usable_score(item: Any) -> tuple[float, float, float]:
    score = _get_field(item, "score")
    error = _get_field(item, "error")
    if score is None or error:
        return 0.0, 0.0, 0.0
    confidence = float(_get_field(item, "confidence", 0.0) or 0.0)
    return float(score), confidence, 1.0


def _group_by_name(items: Sequence[Any], key_field: str) -> dict[str, Any]:
    grouped: dict[str, Any] = {}
    for item in items:
        grouped[_normalize_key(_get_field(item, key_field))] = item
    return grouped


def feature_source(feature_name: str) -> str:
    for source in SOURCE_NAMES:
        prefix = f"{source}_"
        if feature_name.startswith(prefix):
            return source
    return "fusion_context"


def extract_feature_row(signals: Sequence[Any], agents: Sequence[Any]) -> dict[str, float]:
    signal_map = _group_by_name(signals, "layer")
    agent_map = _group_by_name(agents, "agent")
    row: dict[str, float] = {}

    available_signal_count = 0.0
    for layer_name in LAYER_NAMES:
        score, confidence, available = _usable_score(signal_map.get(layer_name))
        row[f"{layer_name}_score"] = score
        row[f"{layer_name}_confidence"] = confidence
        row[f"{layer_name}_available"] = available
        available_signal_count += available

    available_agent_count = 0.0
    for agent_name in AGENT_NAMES:
        score, confidence, available = _usable_score(agent_map.get(agent_name))
        row[f"{agent_name}_score"] = score
        row[f"{agent_name}_confidence"] = confidence
        row[f"{agent_name}_available"] = available
        available_agent_count += available

    metadata_item = signal_map.get("l4_metadata")
    metadata_evidence = _get_field(metadata_item, "evidence", {}) or {}
    metadata_absent = 0.0 if metadata_evidence.get("exif_present") else 1.0
    recapture_score = row["l3_recapture_score"]
    semantic_score = row["semantic_inspector_score"]

    row["metadata_absent"] = metadata_absent
    row["recapture_x_metadata_absent"] = recapture_score * metadata_absent
    row["recapture_flag"] = 1.0 if recapture_score >= 0.7 else 0.0
    row["semantic_flag"] = 1.0 if semantic_score >= 0.6 else 0.0
    row["available_signal_count"] = available_signal_count
    row["available_agent_count"] = available_agent_count
    return row


def row_to_vector(row: Mapping[str, float], feature_names: Sequence[str] = FEATURE_NAMES) -> list[float]:
    return [float(row.get(name, 0.0)) for name in feature_names]
