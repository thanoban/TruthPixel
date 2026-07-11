from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ClaimRecord(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.tenant_id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    signals_json: Mapped[list] = mapped_column(JSON, default=list)
    agent_findings_json: Mapped[list] = mapped_column(JSON, default=list)
    fusion_json: Mapped[dict] = mapped_column(JSON, default=dict)
    report_text: Mapped[str] = mapped_column(Text, default="")
    disclaimer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="completed", index=True)
    task_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    audit_events: Mapped[list["AuditEventRecord"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["ArtifactRecord"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )
    usage_summary: Mapped["ClaimUsageSummaryRecord | None"] = relationship(
        back_populates="claim", cascade="all, delete-orphan", uselist=False
    )
    tenant: Mapped["TenantRecord | None"] = relationship(back_populates="claims")


class TenantRecord(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    rate_limit_requests: Mapped[int] = mapped_column(Integer, default=120)
    rate_limit_window_seconds: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    claims: Mapped[list["ClaimRecord"]] = relationship(back_populates="tenant")
    api_keys: Mapped[list["ApiKeyRecord"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class ApiKeyRecord(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.tenant_id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    key_prefix: Mapped[str] = mapped_column(String(20), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    rate_limit_requests: Mapped[int] = mapped_column(Integer, default=120)
    rate_limit_window_seconds: Mapped[int] = mapped_column(Integer, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["TenantRecord"] = relationship(back_populates="api_keys")


class RateLimitEventRecord(Base):
    __tablename__ = "rate_limit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_type: Mapped[str] = mapped_column(String(30), index=True)
    scope_key: Mapped[str] = mapped_column(String(200), index=True)
    route: Mapped[str] = mapped_column(String(200))
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.tenant_id"), nullable=True, index=True
    )
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    claim: Mapped[ClaimRecord] = relationship(back_populates="audit_events")


class ArtifactRecord(Base):
    __tablename__ = "claim_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    byte_size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_backend: Mapped[str] = mapped_column(String(30))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    claim: Mapped[ClaimRecord] = relationship(back_populates="artifacts")


class ClaimUsageSummaryRecord(Base):
    __tablename__ = "claim_usage_summaries"

    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.claim_id"), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.tenant_id"), nullable=True, index=True
    )
    outcome: Mapped[str] = mapped_column(String(40), default="")
    total_external_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_external_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    providers_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    claim: Mapped[ClaimRecord] = relationship(back_populates="usage_summary")
