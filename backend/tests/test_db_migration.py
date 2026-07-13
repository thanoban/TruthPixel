"""Regression test for a real bug found via live verification: an existing SQLite DB
created before `claims.tenant_id` (and other auth-era columns) existed would throw
`OperationalError: no such column: claims.tenant_id` on every claims query forever,
because `Base.metadata.create_all()` only creates missing TABLES, never alters existing
ones. `init_db()` now runs Alembic migrations (`backend/alembic/`) to head instead — the
baseline migration (`0001_baseline_schema.py`) self-heals this same class of drift, and any
future schema change becomes a real, reviewed migration instead of more ad-hoc patching.
"""

import sqlite3

from sqlalchemy import inspect

from app.config import get_settings
from app.storage import reset_storage_state
from app.storage.repository import get_engine, init_db


def test_init_db_backfills_columns_missing_from_a_pre_existing_table(monkeypatch, tmp_path):
    db_path = tmp_path / "legacy.db"

    # Simulate a DB created before the auth/tenant feature (and several other columns)
    # landed: a `claims` table with only its original-era columns.
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE claims (claim_id VARCHAR(64) PRIMARY KEY, created_at DATETIME)"
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    reset_storage_state()

    init_db()

    engine = get_engine()
    columns = {col["name"] for col in inspect(engine).get_columns("claims")}
    tables = set(inspect(engine).get_table_names())
    assert "tenant_id" in columns
    assert "status" in columns
    assert "decision_json" in columns
    assert "claim_usage_summaries" in tables

    # The actual symptom from live verification: this query used to raise
    # OperationalError: no such column: claims.tenant_id.
    with engine.connect() as conn:
        conn.exec_driver_sql("SELECT tenant_id, status FROM claims").fetchall()

    reset_storage_state()
    get_settings.cache_clear()


def test_init_db_is_a_safe_no_op_on_an_already_current_database(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    reset_storage_state()

    init_db()
    init_db()  # must not raise on a table that's already fully up to date

    reset_storage_state()
    get_settings.cache_clear()


def test_init_db_stamps_alembic_version_at_head(tmp_path, monkeypatch):
    """Confirms init_db() is actually running through Alembic (not silently falling back
    to something else): a fresh DB should end up with an alembic_version table recording
    the baseline revision, so subsequent init_db() calls are a cheap version check rather
    than re-running the whole baseline migration every time.
    """
    db_path = tmp_path / "versioned.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    reset_storage_state()

    init_db()

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT version_num FROM alembic_version").fetchall()
    assert [row[0] for row in rows] == ["0002"]

    reset_storage_state()
    get_settings.cache_clear()
