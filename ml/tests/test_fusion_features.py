from app.schemas import AgentFinding, Layer, SignalResult

from ml.fusion.features import FEATURE_NAMES, extract_feature_row, row_to_vector


def test_extract_feature_row_tracks_availability_and_interactions():
    row = extract_feature_row(
        [
            SignalResult(layer=Layer.L1_AIGEN, score=0.3, confidence=0.9),
            SignalResult(layer=Layer.L3_RECAPTURE, score=0.85, confidence=0.8),
            SignalResult(
                layer=Layer.L4_METADATA,
                score=0.2,
                confidence=0.2,
                evidence={"exif_present": False},
            ),
            SignalResult(layer=Layer.L5_CONTEXT, error="timeout"),
        ],
        [AgentFinding(agent="semantic_inspector", score=0.7, confidence=0.6)],
    )

    assert row["l1_aigen_available"] == 1.0
    assert row["l2_forensics_available"] == 0.0
    assert row["l5_context_available"] == 0.0
    assert row["metadata_absent"] == 1.0
    assert row["recapture_x_metadata_absent"] == 0.85
    assert row["recapture_flag"] == 1.0
    assert row["semantic_flag"] == 1.0
    assert row["available_signal_count"] == 3.0
    assert row["available_agent_count"] == 1.0


def test_row_to_vector_matches_declared_feature_order():
    row = extract_feature_row([], [])

    vector = row_to_vector(row)

    assert len(vector) == len(FEATURE_NAMES)
    assert vector[FEATURE_NAMES.index("metadata_absent")] == 1.0
