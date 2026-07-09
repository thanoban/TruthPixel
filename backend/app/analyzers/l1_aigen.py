from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from ml.layer1_aigen.model import build_probe_head, load_open_clip_encoder

from ..config import get_settings
from ..hf_inference import run_hf_ensemble
from ..schemas import ClaimContext, Layer, SignalResult
from .base import Analyzer


def _confidence_from_score(score: float) -> float:
    return round(max(0.2, min(1.0, abs(score - 0.5) * 2)), 4)


def _resolve_device(torch, configured_device: str) -> str:
    if configured_device and configured_device.lower() != "auto":
        return configured_device
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@lru_cache(maxsize=4)
def _load_runtime(model_path: str, configured_device: str) -> dict:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - exercised in runtime environments
        raise RuntimeError(
            "PyTorch is required for L1 inference. Install backend/requirements.txt."
        ) from exc

    checkpoint_path = Path(model_path).expanduser().resolve()
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"L1 checkpoint not found: {checkpoint_path}")

    try:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    except TypeError:  # pragma: no cover - compatibility fallback
        checkpoint = torch.load(checkpoint_path, map_location="cpu")

    metadata = checkpoint.get("metadata")
    state_dict = checkpoint.get("head_state_dict")
    if not isinstance(metadata, dict) or not isinstance(state_dict, dict):
        raise RuntimeError("L1 checkpoint missing metadata or head_state_dict")

    encoder_cfg = metadata.get("encoder")
    head_cfg = metadata.get("head")
    if not isinstance(encoder_cfg, dict) or not isinstance(head_cfg, dict):
        raise RuntimeError("L1 checkpoint metadata missing encoder/head config")
    if "embedding_dim" not in encoder_cfg:
        raise RuntimeError("L1 checkpoint metadata missing encoder.embedding_dim")

    device = _resolve_device(torch, configured_device)
    encoder_runtime_cfg = {**encoder_cfg, "device": device}
    encode, preprocess = load_open_clip_encoder(SimpleNamespace(**encoder_runtime_cfg))

    head = build_probe_head(int(encoder_cfg["embedding_dim"]), SimpleNamespace(**head_cfg))
    head.load_state_dict(state_dict)
    head.to(device)
    head.eval()

    encoder_name = str(encoder_cfg.get("model_name", "unknown"))
    pretrained_name = str(encoder_cfg.get("pretrained", "unknown"))
    model_version = f"clip-head-{encoder_name}-{pretrained_name}"

    return {
        "torch": torch,
        "encode": encode,
        "preprocess": preprocess,
        "head": head,
        "device": device,
        "checkpoint_path": checkpoint_path,
        "metadata": metadata,
        "model_version": model_version,
    }


class AiGenAnalyzer(Analyzer):
    """L1 — AI-generation detection.

    Three modes, in precedence order:
      1. Local trained CLIP-head checkpoint (L1_MODEL_PATH) — our own head, tuned with
         screenshot augmentation (see ml/layer1_aigen/). Preferred when available.
      2. HF Inference API ensemble (HF_API_TOKEN + L1_HF_MODELS) — an ensemble of
         pretrained detectors called serverlessly. Zero training, zero GPU hosting; the
         fastest path to real accuracy and robust across generators (independent
         architectures → uncorrelated errors). See app/hf_inference.py.
      3. Neutral stub when neither is configured.
    """

    layer = Layer.L1_AIGEN

    async def _run(self, image: bytes, context: ClaimContext, claim_id: str = "") -> SignalResult:
        settings = get_settings()
        if settings.l1_model_path:
            return await self._run_local_checkpoint(image, settings)
        if settings.l1_hf_ensemble_configured:
            return await self._run_hf_ensemble(image, settings)
        return SignalResult(
            layer=self.layer,
            score=0.5,
            confidence=0.1,
            evidence={"note": "stub — neither L1_MODEL_PATH nor an HF ensemble configured"},
        )

    async def _run_hf_ensemble(self, image: bytes, settings) -> SignalResult:
        result = await run_hf_ensemble(
            image,
            models=settings.l1_hf_model_list,
            token=settings.hf_api_token,
            timeout_seconds=settings.hf_inference_timeout_seconds,
        )
        member_evidence = [
            {"model": m.model, "ai_probability": m.ai_probability, "error": m.error}
            for m in result.members
        ]
        if result.ai_probability is None:
            # Every member failed — surface as an error so fusion drops L1, rather than
            # emitting a misleading neutral score.
            errors = "; ".join(f"{m.model}: {m.error}" for m in result.members if m.error)
            raise RuntimeError(f"all HF ensemble members failed: {errors}")

        return SignalResult(
            layer=self.layer,
            score=result.ai_probability,
            confidence=result.confidence,
            evidence={
                "provider": "hf-inference-ensemble",
                "prediction": "ai_generated" if result.ai_probability >= 0.5 else "real_looking",
                "threshold": 0.5,
                "members_total": len(result.members),
                "members_responded": len(result.responded),
                "members": member_evidence,
            },
            model_version="hf-ensemble-" + "+".join(settings.l1_hf_model_list),
        )

    async def _run_local_checkpoint(self, image: bytes, settings) -> SignalResult:
        runtime = _load_runtime(settings.l1_model_path, settings.l1_model_device)
        with Image.open(io.BytesIO(image)) as pil_image:
            image_rgb = pil_image.convert("RGB")

        tensor = runtime["preprocess"](image_rgb).unsqueeze(0).to(runtime["device"])
        torch = runtime["torch"]
        with torch.no_grad():
            features = runtime["encode"](tensor)
            logits = runtime["head"](features)
            score = float(torch.sigmoid(logits).item())

        metadata = runtime["metadata"]
        encoder_cfg = metadata["encoder"]
        head_cfg = metadata["head"]

        return SignalResult(
            layer=self.layer,
            score=score,
            confidence=_confidence_from_score(score),
            evidence={
                "provider": "local-clip-head",
                "checkpoint_path": str(runtime["checkpoint_path"]),
                "device": runtime["device"],
                "prediction": "ai_generated" if score >= 0.5 else "real_looking",
                "threshold": 0.5,
                "heldout_generators": metadata.get("heldout_generators", []),
                "encoder_model": encoder_cfg.get("model_name"),
                "encoder_pretrained": encoder_cfg.get("pretrained"),
                "embedding_dim": encoder_cfg.get("embedding_dim"),
                "head_type": "mlp" if head_cfg.get("use_mlp", True) else "linear",
                "head_hidden_dim": head_cfg.get("hidden_dim"),
                "image_size": [image_rgb.width, image_rgb.height],
                "notes": metadata.get("notes", ""),
            },
            model_version=runtime["model_version"],
        )
