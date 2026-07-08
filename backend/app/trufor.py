from __future__ import annotations

import io
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .config import get_settings

HEATMAP_ALPHA_MAX = 220
SUSPICIOUS_PIXEL_THRESHOLD = 0.65


@dataclass(frozen=True, slots=True)
class TruForResult:
    score: float
    confidence: float
    anomaly_map: np.ndarray
    confidence_map: np.ndarray | None
    heatmap_png: bytes
    heatmap_mean: float
    heatmap_max: float
    confidence_mean: float | None
    suspicious_pixel_fraction: float
    model_version: str


def _resolve_trufor_entrypoint(repo_dir: str) -> tuple[Path, Path]:
    root = Path(repo_dir).expanduser().resolve()
    direct = root / "test.py"
    nested = root / "TruFor_train_test" / "test.py"
    if direct.exists():
        return root, direct
    if nested.exists():
        return nested.parent, nested
    raise RuntimeError(
        "TruFor repo directory must contain test.py or TruFor_train_test/test.py"
    )


def _coerce_probability_map(array: np.ndarray) -> np.ndarray:
    matrix = np.asarray(array, dtype=np.float32)
    matrix = np.squeeze(matrix)
    if matrix.ndim != 2:
        raise RuntimeError(f"expected a 2D heatmap, got shape {tuple(matrix.shape)}")
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=1.0, neginf=0.0)
    low = float(matrix.min())
    high = float(matrix.max())
    if low < 0.0 or high > 1.0:
        spread = high - low
        if spread <= 1e-6:
            return np.zeros_like(matrix)
        matrix = (matrix - low) / spread
    return np.clip(matrix, 0.0, 1.0)


def _resize_map(matrix: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray((matrix * 255).astype(np.uint8), mode="L")
    resized = image.resize(size, Image.Resampling.BILINEAR)
    return np.asarray(resized, dtype=np.float32) / 255.0


def _render_heatmap_png(
    anomaly_map: np.ndarray, confidence_map: np.ndarray | None, image_size: tuple[int, int]
) -> tuple[bytes, np.ndarray, np.ndarray | None]:
    resized_map = _resize_map(anomaly_map, image_size)
    resized_conf = _resize_map(confidence_map, image_size) if confidence_map is not None else None
    alpha = resized_map * (resized_conf if resized_conf is not None else 1.0)

    rgba = np.zeros((image_size[1], image_size[0], 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = np.clip((1.0 - resized_map) * 255.0, 0.0, 255.0).astype(np.uint8)
    rgba[..., 2] = 0
    rgba[..., 3] = np.clip(alpha * HEATMAP_ALPHA_MAX, 0.0, 255.0).astype(np.uint8)

    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG")
    return buffer.getvalue(), resized_map, resized_conf


def run_trufor_inference(image: bytes) -> TruForResult:
    settings = get_settings()
    workdir, script_path = _resolve_trufor_entrypoint(settings.l2_trufor_repo_dir)
    python_executable = settings.l2_trufor_python_executable or sys.executable
    model_file = str(Path(settings.l2_trufor_model_file).expanduser().resolve())

    try:
        image_size = Image.open(io.BytesIO(image)).size
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"unable to decode claim image for TruFor: {exc}") from exc

    with tempfile.TemporaryDirectory(prefix="truthpixel-trufor-") as tmp_dir:
        temp_root = Path(tmp_dir)
        input_path = temp_root / "claim-input.png"
        output_dir = temp_root / "output"
        input_path.write_bytes(image)
        output_dir.mkdir(parents=True, exist_ok=True)

        command = [
            python_executable,
            str(script_path),
            "-in",
            str(input_path),
            "-out",
            str(output_dir),
            "-exp",
            settings.l2_trufor_experiment,
            "-g",
            settings.l2_trufor_device,
            "TEST.MODEL_FILE",
            model_file,
        ]
        process = subprocess.run(
            command,
            cwd=workdir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.l2_trufor_timeout_seconds,
            check=False,
        )
        if process.returncode != 0:
            details = "\n".join(
                part.strip() for part in (process.stdout, process.stderr) if part and part.strip()
            ).strip()
            raise RuntimeError(f"TruFor inference failed: {details or 'unknown subprocess error'}")

        outputs = sorted(output_dir.rglob("*.npz"))
        if not outputs:
            raise RuntimeError("TruFor did not produce any .npz outputs")

        with np.load(outputs[0], allow_pickle=False) as payload:
            if "map" not in payload or "score" not in payload:
                raise RuntimeError("TruFor output is missing required map/score keys")
            anomaly_map = _coerce_probability_map(payload["map"])
            confidence_map = (
                _coerce_probability_map(payload["conf"]) if "conf" in payload else None
            )
            score = float(np.clip(float(np.asarray(payload["score"]).squeeze()), 0.0, 1.0))

        heatmap_png, resized_map, resized_conf = _render_heatmap_png(
            anomaly_map, confidence_map, image_size
        )
        confidence = (
            float(np.clip(float(resized_conf.mean()), 0.0, 1.0))
            if resized_conf is not None
            else max(0.2, min(1.0, abs(score - 0.5) * 2.0))
        )

        return TruForResult(
            score=score,
            confidence=confidence,
            anomaly_map=anomaly_map,
            confidence_map=confidence_map,
            heatmap_png=heatmap_png,
            heatmap_mean=round(float(resized_map.mean()), 4),
            heatmap_max=round(float(resized_map.max()), 4),
            confidence_mean=(
                round(float(resized_conf.mean()), 4) if resized_conf is not None else None
            ),
            suspicious_pixel_fraction=round(
                float((resized_map >= SUSPICIOUS_PIXEL_THRESHOLD).mean()), 4
            ),
            model_version=f"trufor:{Path(model_file).name or 'trufor'}",
        )
