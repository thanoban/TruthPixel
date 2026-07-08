"""Runtime scoring for exported learned fusion models."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ml.fusion.features import FEATURE_NAMES, SOURCE_NAMES, extract_feature_row, feature_source, row_to_vector

from ..schemas import AgentFinding, FusionResult, SignalResult


def _sigmoid(value: float) -> float:
    clipped = max(min(value, 60.0), -60.0)
    return 1.0 / (1.0 + math.exp(-clipped))


@dataclass(frozen=True)
class LearnedFusionModel:
    model_name: str
    feature_names: tuple[str, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    calibration_coefficient: float
    calibration_intercept: float

    @classmethod
    def from_path(cls, path: str | Path) -> "LearnedFusionModel":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        feature_names = tuple(payload["feature_names"])
        if feature_names != FEATURE_NAMES:
            raise ValueError("Exported feature layout does not match runtime feature layout")
        return cls(
            model_name=str(payload["model_name"]),
            feature_names=feature_names,
            feature_means=tuple(float(value) for value in payload["feature_means"]),
            feature_scales=tuple(float(value) for value in payload["feature_scales"]),
            coefficients=tuple(float(value) for value in payload["coefficients"]),
            intercept=float(payload["intercept"]),
            calibration_coefficient=float(payload["calibration"]["coefficient"]),
            calibration_intercept=float(payload["calibration"]["intercept"]),
        )

    def score(self, signals: list[SignalResult], agents: list[AgentFinding], review_threshold: float) -> FusionResult:
        row = extract_feature_row(signals, agents)
        vector = row_to_vector(row, self.feature_names)
        standardized = []
        grouped_contributions = {source: 0.0 for source in SOURCE_NAMES}
        for feature_name, raw_value, mean, scale, coefficient in zip(
            self.feature_names,
            vector,
            self.feature_means,
            self.feature_scales,
            self.coefficients,
            strict=True,
        ):
            z_value = (raw_value - mean) / scale if scale else 0.0
            standardized.append(z_value)
            grouped_contributions[feature_source(feature_name)] += coefficient * z_value

        raw_logit = self.intercept + sum(
            coefficient * value for coefficient, value in zip(self.coefficients, standardized, strict=True)
        )
        calibrated_logit = (
            self.calibration_coefficient * raw_logit + self.calibration_intercept
        )
        risk_score = _sigmoid(calibrated_logit)
        contributions = {
            source: round(value, 4)
            for source, value in grouped_contributions.items()
            if abs(value) >= 1e-6
        }
        return FusionResult(
            risk_score=round(risk_score, 4),
            needs_review=risk_score >= review_threshold,
            contributions=contributions,
            fusion_version=self.model_name,
        )


@lru_cache
def load_learned_fusion_model(path: str) -> LearnedFusionModel:
    return LearnedFusionModel.from_path(path)
