from __future__ import annotations

import csv
import json
from io import StringIO

from sqlalchemy import select

from .schemas import (
    ArtifactKind,
    AgentFinding,
    ClaimContext,
    ClaimDecision,
    FusionResult,
    LabelDecisionCount,
    LabeledClaimExportItem,
    LabeledClaimSummary,
    LabelTenantCount,
    ReviewDecision,
    SignalResult,
)
from .storage.models import ClaimRecord
from .storage.repository import session_scope


def _decision_to_fraud_label(decision: ReviewDecision) -> int | None:
    if decision == ReviewDecision.REJECT:
        return 1
    if decision == ReviewDecision.APPROVE:
        return 0
    return None


def _artifact_download_path(claim_id: str, artifact_id: int) -> str:
    return f"/v1/claims/{claim_id}/artifacts/{artifact_id}"


def _build_export_item(record: ClaimRecord) -> LabeledClaimExportItem | None:
    if not record.decision_json:
        return None

    decision = ClaimDecision.model_validate(record.decision_json)
    context = ClaimContext.model_validate(record.context_json)
    fusion = FusionResult.model_validate(record.fusion_json)
    signals = [SignalResult.model_validate(item) for item in record.signals_json]
    agent_findings = [AgentFinding.model_validate(item) for item in record.agent_findings_json]

    original_artifact_download_path: str | None = None
    heatmap_artifact_download_path: str | None = None
    for artifact in sorted(record.artifacts, key=lambda item: item.id):
        download_path = _artifact_download_path(record.claim_id, artifact.id)
        if artifact.kind == ArtifactKind.ORIGINAL_UPLOAD.value and original_artifact_download_path is None:
            original_artifact_download_path = download_path
        elif artifact.kind == ArtifactKind.HEATMAP.value and heatmap_artifact_download_path is None:
            heatmap_artifact_download_path = download_path

    return LabeledClaimExportItem(
        claim_id=record.claim_id,
        tenant_id=record.tenant_id,
        status=record.status,
        created_at=record.created_at,
        decided_at=decision.decided_at,
        reviewer_id=decision.reviewer_id,
        review_decision=decision.decision,
        fraud_label=_decision_to_fraud_label(decision.decision),
        review_reason=decision.reason,
        context=context,
        fusion=fusion,
        signal_scores={signal.layer.value: signal.score for signal in signals},
        signal_confidences={signal.layer.value: signal.confidence for signal in signals},
        signal_model_versions={signal.layer.value: signal.model_version for signal in signals},
        agent_scores={finding.agent: finding.score for finding in agent_findings},
        agent_models={finding.agent: finding.model for finding in agent_findings},
        artifact_count=len(record.artifacts),
        original_artifact_download_path=original_artifact_download_path,
        heatmap_artifact_download_path=heatmap_artifact_download_path,
    )


def list_labeled_claim_exports(
    *,
    limit: int,
    tenant_id: str | None = None,
    decision: ReviewDecision | None = None,
    training_ready_only: bool = False,
) -> list[LabeledClaimExportItem]:
    with session_scope() as session:
        stmt = (
            select(ClaimRecord)
            .where(ClaimRecord.decision_json.is_not(None))
            .order_by(ClaimRecord.created_at.desc())
        )
        if tenant_id is not None:
            stmt = stmt.where(ClaimRecord.tenant_id == tenant_id)
        records = session.execute(stmt).scalars().all()

        items: list[LabeledClaimExportItem] = []
        for record in records:
            item = _build_export_item(record)
            if item is None:
                continue
            if decision is not None and item.review_decision != decision:
                continue
            if training_ready_only and item.fraud_label is None:
                continue
            items.append(item)
            if len(items) >= limit:
                break
        return items


def summarize_labeled_claim_exports(
    *,
    tenant_id: str | None = None,
    decision: ReviewDecision | None = None,
    training_ready_only: bool = False,
) -> LabeledClaimSummary:
    items = list_labeled_claim_exports(
        limit=5000,
        tenant_id=tenant_id,
        decision=decision,
        training_ready_only=training_ready_only,
    )

    decision_counts: list[LabelDecisionCount] = []
    for review_decision in ReviewDecision:
        matched = [item for item in items if item.review_decision == review_decision]
        if not matched:
            continue
        avg_risk_score = round(
            sum(item.fusion.risk_score for item in matched) / len(matched),
            4,
        )
        decision_counts.append(
            LabelDecisionCount(
                decision=review_decision,
                count=len(matched),
                avg_risk_score=avg_risk_score,
            )
        )

    tenant_counts_map: dict[str | None, int] = {}
    for item in items:
        tenant_counts_map[item.tenant_id] = tenant_counts_map.get(item.tenant_id, 0) + 1
    tenant_counts = [
        LabelTenantCount(tenant_id=current_tenant_id, count=count)
        for current_tenant_id, count in sorted(
            tenant_counts_map.items(),
            key=lambda entry: ((entry[0] or ""), entry[1]),
        )
    ]

    return LabeledClaimSummary(
        total_labeled_claims=len(items),
        training_ready_claims=sum(1 for item in items if item.fraud_label is not None),
        counts_by_decision=decision_counts,
        counts_by_tenant=tenant_counts,
    )


def export_labeled_claims_csv(items: list[LabeledClaimExportItem]) -> str:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "claim_id",
            "tenant_id",
            "status",
            "created_at",
            "decided_at",
            "reviewer_id",
            "review_decision",
            "fraud_label",
            "review_reason",
            "order_id",
            "product_sku",
            "claim_reason",
            "listing_image_urls",
            "risk_score",
            "needs_review",
            "fusion_version",
            "fusion_contributions",
            "signal_scores",
            "signal_confidences",
            "signal_model_versions",
            "agent_scores",
            "agent_models",
            "artifact_count",
            "original_artifact_download_path",
            "heatmap_artifact_download_path",
        ],
    )
    writer.writeheader()
    for item in items:
        writer.writerow(
            {
                "claim_id": item.claim_id,
                "tenant_id": item.tenant_id or "",
                "status": item.status.value,
                "created_at": item.created_at.isoformat(),
                "decided_at": item.decided_at.isoformat(),
                "reviewer_id": item.reviewer_id,
                "review_decision": item.review_decision.value,
                "fraud_label": "" if item.fraud_label is None else item.fraud_label,
                "review_reason": item.review_reason,
                "order_id": item.context.order_id,
                "product_sku": item.context.product_sku,
                "claim_reason": item.context.claim_reason,
                "listing_image_urls": json.dumps(item.context.listing_image_urls),
                "risk_score": item.fusion.risk_score,
                "needs_review": item.fusion.needs_review,
                "fusion_version": item.fusion.fusion_version,
                "fusion_contributions": json.dumps(item.fusion.contributions, sort_keys=True),
                "signal_scores": json.dumps(item.signal_scores, sort_keys=True),
                "signal_confidences": json.dumps(item.signal_confidences, sort_keys=True),
                "signal_model_versions": json.dumps(item.signal_model_versions, sort_keys=True),
                "agent_scores": json.dumps(item.agent_scores, sort_keys=True),
                "agent_models": json.dumps(item.agent_models, sort_keys=True),
                "artifact_count": item.artifact_count,
                "original_artifact_download_path": item.original_artifact_download_path or "",
                "heatmap_artifact_download_path": item.heatmap_artifact_download_path or "",
            }
        )
    return buffer.getvalue()
