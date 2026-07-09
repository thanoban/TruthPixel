from __future__ import annotations

from .artifacts import get_artifact_store
from .schemas import ArtifactKind, Layer, SignalResult
from .storage import add_artifact

INTERNAL_HEATMAP_BYTES_KEY = "_heatmap_png_bytes"
HEATMAP_FILENAME = "trufor-heatmap.png"
HEATMAP_MEDIA_TYPE = "image/png"


def persist_signal_artifacts(
    claim_id: str, signals: list[SignalResult], tenant_id: str | None = None
) -> None:
    for signal in signals:
        if signal.layer != Layer.L2_FORENSICS:
            continue

        evidence = signal.evidence
        heatmap_png = evidence.pop(INTERNAL_HEATMAP_BYTES_KEY, None)
        if not isinstance(heatmap_png, bytes) or not heatmap_png:
            continue

        try:
            stored = get_artifact_store().put_bytes(
                claim_id=claim_id,
                kind=ArtifactKind.HEATMAP.value,
                data=heatmap_png,
                filename=HEATMAP_FILENAME,
                media_type=HEATMAP_MEDIA_TYPE,
            )
            artifact = add_artifact(
                claim_id=claim_id,
                kind=ArtifactKind.HEATMAP,
                filename=stored.filename,
                media_type=stored.media_type,
                byte_size=stored.byte_size,
                sha256=stored.sha256,
                storage_backend=stored.storage_backend,
                storage_key=stored.storage_key,
                tenant_id=tenant_id,
            )
            if artifact is None:
                raise RuntimeError("claim record was not available for heatmap persistence")
        except Exception as exc:  # noqa: BLE001
            evidence["heatmap_available"] = False
            evidence["heatmap_download_path"] = None
            evidence["heatmap_url"] = None
            evidence["heatmap_artifact_id"] = None
            evidence["heatmap_filename"] = None
            evidence["heatmap_media_type"] = None
            evidence["heatmap_storage_error"] = f"{type(exc).__name__}: {exc}"
            continue

        evidence["heatmap_available"] = True
        evidence["heatmap_artifact_id"] = artifact.id
        evidence["heatmap_download_path"] = artifact.download_path
        evidence["heatmap_url"] = artifact.download_path
        evidence["heatmap_filename"] = artifact.filename
        evidence["heatmap_media_type"] = artifact.media_type
        evidence.pop("heatmap_storage_error", None)
