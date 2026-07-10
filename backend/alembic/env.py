from __future__ import annotations

import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable regardless of how/where this is invoked from (CLI with cwd=backend/,
# or programmatically from within the running app with cwd=project root) — see
# backend/app/__init__.py for the same defensive sys.path pattern the app itself uses.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings  # noqa: E402
from app.storage.models import Base  # noqa: E402

config = context.config

# Deliberately NOT calling logging.config.fileConfig(config.config_file_name) here.
# fileConfig() reconfigures the ROOT logger's handler list (even with
# disable_existing_loggers=False), which — since init_db() runs this on every app
# startup, not just standalone CLI invocations — strips out whatever handler the app (or
# pytest's caplog fixture) already installed on root. Found via a real test failure: app
# log events were still being emitted (visible in captured stderr) but caplog stopped
# capturing them the moment this ran. Alembic's own loggers (alembic.runtime.migration,
# etc.) still work fine without this — they just propagate to root and use whatever
# handler is already there.

# One source of truth for the DB URL: the app's own Settings (DATABASE_URL), not a
# separately-maintained value in alembic.ini — see the comment there.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"poolclass": pool.NullPool}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = config.get_main_option("sqlalchemy.url")
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        **_engine_kwargs(config.get_main_option("sqlalchemy.url")),
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
