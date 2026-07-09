import json
from pathlib import Path

from ml.layer1_aigen.model import CheckpointMetadata, EncoderConfig, HeadConfig, write_metadata_json


def test_write_metadata_json_includes_runtime_handoff_fields(tmp_path: Path):
    metadata = CheckpointMetadata(
        encoder=EncoderConfig(model_name="ViT-L-14", pretrained="openai", embedding_dim=768),
        head=HeadConfig(hidden_dim=256, dropout=0.1, use_mlp=True),
        heldout_generators=["flux", "sdxl"],
        split_summary={"train": {"total": 10, "real": 5, "generated": 5}},
        notes="unit-test",
        training={"batch_size": 32, "learning_rate": 1e-4},
        history_summary={"epochs_completed": 4, "best_val_accuracy": 0.91},
    )

    target = tmp_path / "metadata.json"
    write_metadata_json(target, metadata)

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["format_version"] == 1
    assert payload["training"]["batch_size"] == 32
    assert payload["history_summary"]["best_val_accuracy"] == 0.91
    assert payload["encoder"]["model_name"] == "ViT-L-14"
