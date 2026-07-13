"""Hugging Face Inference API ensemble for AI-generation detection.

Why this exists: strong AI-image detectors are already pretrained and served live on
the HF Inference API. Calling an *ensemble* of them (different architectures → less
correlated errors → better generalization to unseen generators) gives L1 real accuracy
with zero training and zero GPU hosting — the fastest credible path, and a natural fit
for our multi-signal fusion thesis (L1 becomes a mini-ensemble inside the bigger fuse).

Each member model returns image-classification labels whose *names differ* per model
("artificial"/"human", "ai"/"real", "AI"/"Real", ...). We normalize by keyword, not by
exact string, so adding a new model needs no per-model label config.

Design rules mirroring the rest of the pipeline:
- One member failing (cold model, rate limit, transport error) must not kill L1 — we
  aggregate whoever answered and only error if *every* member failed.
- Output is a single AI-generated probability in [0, 1] plus a confidence derived from
  member agreement and count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import pstdev

import httpx

from .config import get_settings
from .observability import record_external_usage

HF_INFERENCE_BASE = "https://api-inference.huggingface.co/models"

# Keyword → class. Matched against lowercased label substrings so heterogeneous model
# label vocabularies map without per-model configuration.
_AI_KEYWORDS = (
    "artificial", "ai", "fake", "generated", "synthetic", "gan", "diffusion",
    "deepfake", "computer", "spoof",
)
_REAL_KEYWORDS = (
    "human", "real", "authentic", "camera", "natural", "genuine", "pristine",
)


@dataclass(frozen=True, slots=True)
class MemberResult:
    model: str
    ai_probability: float | None = None
    error: str | None = None
    raw: list[dict] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class EnsembleResult:
    ai_probability: float | None
    confidence: float
    members: list[MemberResult]

    @property
    def responded(self) -> list[MemberResult]:
        return [m for m in self.members if m.ai_probability is not None]


def _classify_label(label: str) -> str | None:
    """Return 'ai', 'real', or None for a single label string."""
    text = label.lower()
    # Check REAL first: "real" must not be shadowed, and avoid "ai" matching inside
    # unrelated words by requiring the AI check to run on the same explicit list.
    if any(keyword in text for keyword in _REAL_KEYWORDS):
        return "real"
    if any(keyword in text for keyword in _AI_KEYWORDS):
        return "ai"
    return None


def ai_probability_from_predictions(predictions: list[dict]) -> float | None:
    """Collapse a model's [{label, score}, ...] output into P(AI-generated).

    Robust to models that return one class or both. Returns None when no label can be
    mapped to either class (unknown label vocabulary).
    """
    ai_score = 0.0
    real_score = 0.0
    matched = False
    for entry in predictions:
        label = entry.get("label")
        score = entry.get("score")
        if not isinstance(label, str) or not isinstance(score, (int, float)):
            continue
        bucket = _classify_label(label)
        if bucket == "ai":
            ai_score += float(score)
            matched = True
        elif bucket == "real":
            real_score += float(score)
            matched = True
    if not matched:
        return None
    total = ai_score + real_score
    if total <= 0:
        return None
    return max(0.0, min(1.0, ai_score / total))


def _confidence(probabilities: list[float]) -> float:
    """Confidence from member count, agreement, and decisiveness.

    More members and tighter agreement → higher confidence; probabilities clustered
    near 0.5 (undecided) or spread apart (disagreement) → lower.
    """
    if not probabilities:
        return 0.0
    mean = sum(probabilities) / len(probabilities)
    decisiveness = abs(mean - 0.5) * 2  # 0 at the boundary, 1 at the extremes
    agreement = 1.0 - min(1.0, pstdev(probabilities) * 2) if len(probabilities) > 1 else 1.0
    count_factor = min(1.0, len(probabilities) / 3)
    return round(max(0.1, min(1.0, decisiveness * 0.5 + agreement * 0.3 + count_factor * 0.2)), 4)


async def _query_member(
    client: httpx.AsyncClient, model: str, image: bytes, token: str
) -> MemberResult:
    headers = {"Authorization": f"Bearer {token}"}
    settings = get_settings()
    try:
        response = await client.post(
            f"{HF_INFERENCE_BASE}/{model}", content=image, headers=headers
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        record_external_usage(
            provider="hf_inference",
            operation="l1_member_query",
            model=model,
            failed=True,
        )
        return MemberResult(model=model, error=f"{type(exc).__name__}: {exc}")

    try:
        payload = response.json()
    except ValueError as exc:
        return MemberResult(model=model, error=f"invalid JSON: {exc}")

    # A cold model returns {"error": "...", "estimated_time": N} instead of a list.
    if isinstance(payload, dict) and payload.get("error"):
        record_external_usage(
            provider="hf_inference",
            operation="l1_member_query",
            model=model,
            failed=True,
        )
        return MemberResult(model=model, error=str(payload["error"]))
    if not isinstance(payload, list):
        record_external_usage(
            provider="hf_inference",
            operation="l1_member_query",
            model=model,
            failed=True,
        )
        return MemberResult(model=model, error="unexpected response shape (not a list)")

    probability = ai_probability_from_predictions(payload)
    if probability is None:
        record_external_usage(
            provider="hf_inference",
            operation="l1_member_query",
            model=model,
            failed=True,
        )
        return MemberResult(model=model, error="no mappable AI/real label", raw=payload)
    record_external_usage(
        provider="hf_inference",
        operation="l1_member_query",
        model=model,
        estimated_cost_usd=max(0.0, float(getattr(settings, "hf_request_cost_usd", 0.0))),
    )
    return MemberResult(model=model, ai_probability=probability, raw=payload)


async def run_hf_ensemble(
    image: bytes, models: list[str], token: str, timeout_seconds: float
) -> EnsembleResult:
    """Query every member in parallel; average whoever answered."""
    import asyncio

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        members = await asyncio.gather(
            *(_query_member(client, model, image, token) for model in models)
        )

    probabilities = [m.ai_probability for m in members if m.ai_probability is not None]
    if not probabilities:
        return EnsembleResult(ai_probability=None, confidence=0.0, members=list(members))

    ensemble_probability = round(sum(probabilities) / len(probabilities), 4)
    return EnsembleResult(
        ai_probability=ensemble_probability,
        confidence=_confidence(probabilities),
        members=list(members),
    )
