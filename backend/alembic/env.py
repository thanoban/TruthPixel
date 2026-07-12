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

# One source of truth for the DB URL: the app's own Settings, not a separately-maintained
# value in alembic.ini — see the comment there. Prefer DIRECT_URL when set (session-mode /
# non-pooled connection — migrations run DDL in a single long-lived transaction, which a
# transaction-mode pooler like Supabase's port 6543 doesn't reliably support), falling back
# to DATABASE_URL for anything that doesn't distinguish the two (local SQLite, a plain
# non-pooled Postgres). See Settings.direct_url's docstring in app/config.py.
_settings = get_settings()
_migration_url = _settings.direct_url or _settings.database_url

# Alembic's Config wraps a stdlib configparser.ConfigParser with interpolation ON, which
# treats a literal "%" as the start of a %(...)s reference — so any DB URL containing a
# URL-encoded character (e.g. "%40" for "@" in a password, which is routine: Postgres
# passwords with special characters get percent-encoded in connection strings) raises
# `ValueError: invalid interpolation syntax` the moment set_main_option() is called. Found
# live wiring up a real Supabase connection string with a percent-encoded password — never
# hit before because no prior URL (sqlite paths, unencoded test values) contained a "%".
# Fix: escape "%" as "%%" before storing; configparser's interpolation un-escapes "%%" back
# to "%" on every subsequent get_main_option()/get_section() read below, so this round-trips
# correctly rather than needing every read site to know about the escaping.
config.set_main_option("sqlalchemy.url", _migration_url.replace("%", "%%"))

target_metadata = Base.metadata


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"poolclass": pool.NullPool}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    elif database_url.startswith("postgresql"):
        # Same reasoning as app/storage/repository.py::_engine_kwargs — disable psycopg3
        # autoprepare, since it's unsafe against any transaction-mode pooler and a harmless
        # no-op otherwise. Migrations should use DIRECT_URL (session-mode) anyway, but this
        # is defense-in-depth if that's unset and it falls back to a pooled DATABASE_URL.
        kwargs["connect_args"] = {"prepare_threshold": None}
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
