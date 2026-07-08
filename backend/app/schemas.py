from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Layer(str, Enum):
    L1_AIGEN = "l1_aigen"
    L2_FORENSICS = "l2_forensics"
    L3_RECAPTURE = "l3_recapture"
    L4_METADATA = "l4_metadata"
    L5_CONTEXT = "l5_context"


class SignalResult(BaseModel):
    """Normalized output of one analyzer layer.

    score: 0 = authentic-looking, 1 = fraud-indicating. None = signal unavailable.
    confidence: how much this layer trusts its own score (0-1).
    """

    layer: Layer
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    model_version: str = "stub-0.1"


class AgentFinding(BaseModel):
    """Structured output of one VLM agent (Gemini on Vertex, or stub)."""

    agent: str
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(default=0.0, ge=0, le=1)
    findings: list[str] = Field(default_factory=list)
    model: str = "stub"


class FusionResult(BaseModel):
    risk_score: float = Field(ge=0, le=1)
    needs_review: bool
    contributions: dict[str, float] = Field(default_factory=dict)
    fusion_version: str = "weighted-avg-0.1"


class ClaimContext(BaseModel):
    order_id: str = ""
    product_sku: str = ""
    claim_reason: str = ""
    listing_image_urls: list[str] = Field(default_factory=list)


class ArtifactKind(str, Enum):
    ORIGINAL_UPLOAD = "original_upload"
    HEATMAP = "heatmap"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    NEEDS_MORE_INFO = "needs_more_info"


class ClaimDecision(BaseModel):
    reviewer_id: str
    decision: ReviewDecision
    reason: str = ""
    decided_at: datetime


class ClaimDecisionRequest(BaseModel):
    reviewer_id: str = Field(min_length=1, max_length=200)
    decision: ReviewDecision
    reason: str = Field(default="", max_length=5000)


class AuditEvent(BaseModel):
    id: int
    claim_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ClaimArtifact(BaseModel):
    id: int
    claim_id: str
    kind: ArtifactKind
    filename: str
    media_type: str
    byte_size: int = Field(ge=0)
    sha256: str
    storage_backend: str
    download_path: str
    created_at: datetime


class ClaimReport(BaseModel):
    claim_id: str
    context: ClaimContext
    signals: list[SignalResult]
    agent_findings: list[AgentFinding]
    fusion: FusionResult
    report_text: str
    disclaimer: str = (
        "Confidence-scored assessment, not a verdict. A human reviewer makes the final call."
    )


class StoredClaim(ClaimReport):
    created_at: datetime
    updated_at: datetime
    decision: ClaimDecision | None = None
    artifacts: list[ClaimArtifact] = Field(default_factory=list)


class ClaimListItem(BaseModel):
    claim_id: str
    created_at: datetime
    updated_at: datetime
    context: ClaimContext
    fusion: FusionResult
    decision: ClaimDecision | None = None
    signal_count: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
