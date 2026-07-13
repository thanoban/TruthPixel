"""add claim usage summary storage

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "claim_usage_summaries" in inspector.get_table_names():
        return

    op.create_table(
        "claim_usage_summaries",
        sa.Column("claim_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("outcome", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("total_external_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_external_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("providers_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.claim_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.tenant_id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_claim_usage_summaries_tenant_id",
        "claim_usage_summaries",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "claim_usage_summaries" not in inspector.get_table_names():
        return
    op.drop_index("ix_claim_usage_summaries_tenant_id", table_name="claim_usage_summaries")
    op.drop_table("claim_usage_summaries")
