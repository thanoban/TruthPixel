"""Runtime scoring for exported learned fusion models."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ml.fusion.features import (
    FEATURE_NAMES,
    SOURCE_NAMES,
    extract_feature_row,
    feature_source,
    row_to_vector,
)

from ..schemas import AgentFinding, FusionResult, SignalResult

ARTIFACT_SCHEMA_VERSION = "learned-fusion/v1"
SUPPORTED_CALIBRATION_METHODS = {"platt"}


def _sigmoid(value: float) -> float:
    clipped = max(min(value, 60.0), -60.0)
    return 1.0 / (1.0 + math.exp(-clipped))


class LearnedFusionLoadError(RuntimeError):
    """Raised when a learned-fusion artifact is present but not safe to trust."""


def _require_mapping(payload: Any, context: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LearnedFusionLoadError(f"{context} must be a JSON object")
    return payload


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LearnedFusionLoadError(f"Missing or invalid '{key}' string")
    return value


def _require_number_sequence(
    payload: dict[str, Any],
    key: str,
    *,
    expected_length: int | None = None,
    positive_only: bool = False,
) -> tuple[float, ...]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        raise LearnedFusionLoadError(f"Missing or invalid '{key}' list")
    values: list[float] = []
    for index, item in enumerate(raw):
        try:
            value = float(item)
        except (TypeError, ValueError) as exc:
            raise LearnedFusionLoadError(f"'{key}'[{index}] is not numeric") from exc
        if not math.isfinite(value):
            raise LearnedFusionLoadError(f"'{key}'[{index}] must be finite")
        if positive_only and value <= 0:
            raise LearnedFusionLoadError(f"'{key}'[{index}] must be > 0")
        values.append(value)
    if expected_length is not None and len(values) != expected_length:
        raise LearnedFusionLoadError(
            f"'{key}' length {len(values)} does not match expected {expected_length}"
        )
    return tuple(values)


def _load_manifest(manifest_path: Path) -> tuple[dict[str, Any], Path]:
    manifest = _require_mapping(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        "learned fusion manifest",
    )
    schema_version = _require_str(manifest, "artifact_schema_version")
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        raise LearnedFusionLoadError(
            f"Unsupported learned fusion manifest schema version: {schema_version}"
        )
    model_name = _require_str(manifest, "model")
    model_path = (manifest_path.parent / model_name).resolve()
    if not model_path.is_file():
        raise LearnedFusionLoadError(f"Manifest points to missing model artifact: {model_path}")
    return manifest, model_path


@dataclass(frozen=True)
class LearnedFusionModel:
    model_name: str
    feature_names: tuple[str, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    calibration_method: str
    calibration_coefficient: float
    calibration_intercept: float
    artifact_path: str
    artifact_schema_version: str

    @classmethod
    def from_path(cls, path: str | Path) -> "LearnedFusionModel":
        resolved = Path(path).expanduser().resolve()
        if not resolved.exists():
            raise LearnedFusionLoadError(f"Learned fusion artifact does not exist: {resolved}")
        if resolved.is_dir():
            raise LearnedFusionLoadError(
                f"Learned fusion path must point to manifest.json or model.json, not directory: {resolved}"
            )

        manifest: dict[str, Any] | None = None
        model_path = resolved
        if resolved.name == "manifest.json":
            manifest, model_path = _load_manifest(resolved)

        payload = _require_mapping(
            json.loads(model_path.read_text(encoding="utf-8")),
            "learned fusion model",
        )
        schema_version = str(payload.get("artifact_schema_version") or "").strip() or "legacy"
        if schema_version not in {ARTIFACT_SCHEMA_VERSION, "legacy"}:
            raise LearnedFusionLoadError(
                f"Unsupported learned fusion model schema version: {schema_version}"
            )

        model_type = _require_str(payload, "model_type")
        if model_type != "logistic_regression":
            raise LearnedFusionLoadError(f"Unsupported learned fusion model_type: {model_type}")

        feature_names = tuple(payload.get("feature_names", []))
        if feature_names != FEATURE_NAMES:
            raise LearnedFusionLoadError(
                "Exported feature layout does not match runtime feature layout"
            )

        coefficients = _require_number_sequence(
            payload,
            "coefficients",
            expected_length=len(feature_names),
        )
        means = _require_number_sequence(
            payload,
            "feature_means",
            expected_length=len(feature_names),
        )
        scales = _require_number_sequence(
            payload,
            "feature_scales",
            expected_length=len(feature_names),
            positive_only=True,
        )
        intercept = float(payload.get("intercept"))
        if not math.isfinite(intercept):
            raise LearnedFusionLoadError("'intercept' must be finite")

        calibration = _require_mapping(payload.get("calibration"), "learned fusion calibration")
        calibration_method = _require_str(calibration, "method")
        if calibration_method not in SUPPORTED_CALIBRATION_METHODS:
            raise LearnedFusionLoadError(
                f"Unsupported calibration method: {calibration_method}"
            )
        calibration_coefficient = float(calibration.get("coefficient"))
        calibration_intercept = float(calibration.get("intercept"))
        if not math.isfinite(calibration_coefficient) or not math.isfinite(calibration_intercept):
            raise LearnedFusionLoadError("Calibration parameters must be finite")

        if manifest is not None:
            expected_model_name = manifest.get("model_name")
            if expected_model_name and str(expected_model_name) != str(payload.get("model_name")):
                raise LearnedFusionLoadError(
                    "Manifest model_name does not match model.json model_name"
                )

        return cls(
            model_name=_require_str(payload, "model_name"),
            feature_names=feature_names,
            feature_means=means,
            feature_scales=scales,
            coefficients=coefficients,
            intercept=intercept,
            calibration_method=calibration_method,
            calibration_coefficient=calibration_coefficient,
            calibration_intercept=calibration_intercept,
            artifact_path=str(model_path),
            artifact_schema_version=schema_version,
        )

    def score(
        self,
        signals: list[SignalResult],
        agents: list[AgentFinding],
        review_threshold: float,
    ) -> FusionResult:
        row = extract_feature_row(signals, agents)
        vector = row_to_vector(row, self.feature_names)

        grouped_contributions = {source: 0.0 for source in SOURCE_NAMES}
        standardized: list[float] = []
        for feature_name, raw_value, mean, scale, coefficient in zip(
            self.feature_names,
            vector,
            self.feature_means,
            self.feature_scales,
            self.coefficients,
            strict=True,
        ):
            z_value = (raw_value - mean) / scale
            standardized.append(z_value)
            grouped_contributions[feature_source(feature_name)] += coefficient * z_value

        source_total = sum(grouped_contributions.values())
        raw_logit = self.intercept + source_total
        calibrated_logit = (
            self.calibration_coefficient * raw_logit + self.calibration_intercept
        )
        risk_score = _sigmoid(calibrated_logit)

        contributions: dict[str, float] = {
            source: round(value, 4)
            for source, value in grouped_contributions.items()
            if abs(value) >= 1e-6
        }
        fusion_context = calibrated_logit - source_total
        if abs(fusion_context) >= 1e-6:
            contributions["fusion_context"] = round(fusion_context, 4)

        return FusionResult(
            risk_score=round(risk_score, 4),
            needs_review=risk_score >= review_threshold,
            contributions=contributions,
            fusion_version=self.model_name,
        )


@lru_cache
def load_learned_fusion_model(path: str) -> LearnedFusionModel:
    return LearnedFusionModel.from_path(path)
