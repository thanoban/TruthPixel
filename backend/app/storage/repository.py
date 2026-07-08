from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..schemas import (
    ArtifactKind,
    AuditEvent,
    ClaimArtifact,
    ClaimDecision,
    ClaimDecisionRequest,
    ClaimListItem,
    ClaimReport,
    ClaimContext,
    StoredClaim,
)
from .models import ArtifactRecord, AuditEventRecord, Base, ClaimRecord, utc_now


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"future": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


@lru_cache
def get_engine():
    settings = get_settings()
    return create_engine(settings.database_url, **_engine_kwargs(settings.database_url))


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def reset_storage_state() -> None:
    get_session_factory.cache_clear()
    engine = None
    if get_engine.cache_info().currsize:
        engine = get_engine()
    get_engine.cache_clear()
    if engine is not None:
        engine.dispose()


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


@contextmanager
def session_scope():
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _claim_to_schema(record: ClaimRecord) -> StoredClaim:
    decision = ClaimDecision.model_validate(record.decision_json) if record.decision_json else None
    return StoredClaim(
        claim_id=record.claim_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
        context=ClaimContext.model_validate(record.context_json),
        signals=record.signals_json,
        agent_findings=record.agent_findings_json,
        fusion=record.fusion_json,
        report_text=record.report_text,
        disclaimer=record.disclaimer,
        decision=decision,
        artifacts=[_artifact_to_schema(item) for item in sorted(record.artifacts, key=lambda a: a.id)],
    )


def _artifact_to_schema(record: ArtifactRecord) -> ClaimArtifact:
    return ClaimArtifact(
        id=record.id,
        claim_id=record.claim_id,
        kind=record.kind,
        filename=record.filename,
        media_type=record.media_type,
        byte_size=record.byte_size,
        sha256=record.sha256,
        storage_backend=record.storage_backend,
        download_path=f"/v1/claims/{record.claim_id}/artifacts/{record.id}",
        created_at=record.created_at,
    )


def _append_audit_event(session: Session, claim_id: str, event_type: str, payload: dict) -> None:
    session.add(
        AuditEventRecord(
            claim_id=claim_id,
            event_type=event_type,
            payload_json=payload,
        )
    )


def create_or_update_claim(report: ClaimReport) -> StoredClaim:
    with session_scope() as session:
        record = session.get(ClaimRecord, report.claim_id)
        if record is None:
            record = ClaimRecord(claim_id=report.claim_id)
            session.add(record)

        record.context_json = report.context.model_dump(mode="json")
        record.signals_json = [signal.model_dump(mode="json") for signal in report.signals]
        record.agent_findings_json = [
            finding.model_dump(mode="json") for finding in report.agent_findings
        ]
        record.fusion_json = report.fusion.model_dump(mode="json")
        record.report_text = report.report_text
        record.disclaimer = report.disclaimer
        session.flush()

        _append_audit_event(
            session,
            report.claim_id,
            "claim_persisted",
            {
                "risk_score": report.fusion.risk_score,
                "needs_review": report.fusion.needs_review,
                "signal_count": len(report.signals),
            },
        )
        session.flush()
        session.refresh(record)
        return _claim_to_schema(record)


def get_claim(claim_id: str) -> StoredClaim | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        return _claim_to_schema(record) if record else None


def list_claims(
    *, limit: int = 20, needs_review: bool | None = None, decided: bool | None = None
) -> list[ClaimListItem]:
    with session_scope() as session:
        stmt = select(ClaimRecord).order_by(ClaimRecord.created_at.desc())
        records = session.execute(stmt).scalars().all()

        items: list[ClaimListItem] = []
        for record in records:
            if needs_review is not None and bool(record.fusion_json.get("needs_review")) != needs_review:
                continue
            has_decision = record.decision_json is not None
            if decided is not None and has_decision != decided:
                continue
            decision = (
                ClaimDecision.model_validate(record.decision_json)
                if record.decision_json
                else None
            )
            items.append(
                ClaimListItem(
                    claim_id=record.claim_id,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                    context=ClaimContext.model_validate(record.context_json),
                    fusion=record.fusion_json,
                    decision=decision,
                    signal_count=len(record.signals_json),
                    artifact_count=len(record.artifacts),
                )
            )
        return items[:limit]


def record_decision(claim_id: str, request: ClaimDecisionRequest) -> StoredClaim | None:
    with session_scope() as session:
        record = session.get(ClaimRecord, claim_id)
        if record is None:
            return None
        decision = ClaimDecision(
            reviewer_id=request.reviewer_id,
            decision=request.decision,
            reason=request.reason,
            decided_at=utc_now(),
        )
        record.decision_json = decision.model_dump(mode="json")
        session.flush()
        _append_audit_event(
            session,
            claim_id,
            "decision_recorded",
            {
                "reviewer_id": request.reviewer_id,
                "decision": request.decision.value,
                "reason": request.reason,
            },
        )
        session.flush()
        session.refresh(record)
        return _claim_to_schema(record)


def get_claim_audit_events(claim_id: str) -> list[AuditEvent]:
    with session_scope() as session:
        stmt = (
            select(AuditEventRecord)
            .where(AuditEventRecord.claim_id == claim_id)
            .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
        )
        records = session.execute(stmt).scalars().all()
        return [
            AuditEvent(
                id=record.id,
                claim_id=record.claim_id,
                event_type=record.event_type,
                payload=record.payload_json,
                created_at=record.created_at,
            )
            for record in records
        ]


def add_artifact(
    *,
    claim_id: str,
    kind: ArtifactKind,
    filename: str,
    media_type: str,
    byte_size: int,
    sha256: str,
    storage_backend: str,
    storage_key: str,
) -> ClaimArtifact | None:
    with session_scope() as session:
        claim = session.get(ClaimRecord, claim_id)
        if claim is None:
            return None
        record = ArtifactRecord(
            claim_id=claim_id,
            kind=kind.value,
            filename=filename,
            media_type=media_type,
            byte_size=byte_size,
            sha256=sha256,
            storage_backend=storage_backend,
            storage_key=storage_key,
        )
        session.add(record)
        session.flush()
        _append_audit_event(
            session,
            claim_id,
            "artifact_stored",
            {
                "artifact_id": record.id,
                "kind": kind.value,
                "storage_backend": storage_backend,
                "byte_size": byte_size,
            },
        )
        session.flush()
        session.refresh(record)
        return _artifact_to_schema(record)


def list_claim_artifacts(claim_id: str) -> list[ClaimArtifact] | None:
    with session_scope() as session:
        claim = session.get(ClaimRecord, claim_id)
        if claim is None:
            return None
        stmt = (
            select(ArtifactRecord)
            .where(ArtifactRecord.claim_id == claim_id)
            .order_by(ArtifactRecord.created_at.asc(), ArtifactRecord.id.asc())
        )
        records = session.execute(stmt).scalars().all()
        return [_artifact_to_schema(record) for record in records]


def get_artifact_record(claim_id: str, artifact_id: int) -> ArtifactRecord | None:
    with session_scope() as session:
        stmt = select(ArtifactRecord).where(
            ArtifactRecord.claim_id == claim_id, ArtifactRecord.id == artifact_id
        )
        record = session.execute(stmt).scalar_one_or_none()
        if record is None:
            return None
        session.expunge(record)
        return record
