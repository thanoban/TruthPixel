"""baseline schema — brings any existing DB up to the current models, idempotently

Revision ID: 0001
Revises:
Create Date: 2026-07-10

This project ran without a migration framework for a while: schema changes were made by
letting `Base.metadata.create_all()` run at startup, which only creates missing tables and
never alters existing ones. That silently broke any DB created before a column was added
later (e.g. `claims.tenant_id`, added when the auth/tenant feature landed) — see
docs/CORRECTIONS.md 2026-07-09 for the incident this baseline replaces the runtime
workaround for. Already-deployed/local databases can be in almost any state between
"predates auth" and "fully current," so rather than a strict ALTER-TABLE sequence that
assumes one specific starting point, this baseline:

  1. Creates any tables that don't exist yet (idempotent — checkfirst=True).
  2. Adds any columns the current ORM models define that an existing table is missing.

Once an environment has run this baseline, schema changes should be normal, single-purpose
migrations — `alembic revision --autogenerate -m "..."` against a DB already at head,
reviewed before committing — not more catch-up logic like this. This exists exactly once,
to adopt Alembic without forcing a "drop and recreate your DB" step on anyone.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

from app.storage.models import Base

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # brand-new table, just created above — already fully current
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            ddl_type = column.type.compile(dialect=bind.dialect)
            bind.execute(
                text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl_type}')
            )


def downgrade() -> None:
    # Baseline migration — no safe generic downgrade (would mean dropping tables that may
    # hold real data). Restore from a backup instead if you truly need to roll back past this.
    raise NotImplementedError("baseline migration has no downgrade")
