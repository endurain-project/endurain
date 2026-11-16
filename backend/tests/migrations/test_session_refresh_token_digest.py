"""Tests for the migration that ends the sessions holding an Argon2 refresh-token hash."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/17_session_digest_and_strava_scope.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("session_refresh_token_digest", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _engine_with_sessions() -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE users_sessions (id VARCHAR(36) PRIMARY KEY, refresh_token VARCHAR)"))
        connection.execute(
            sa.text("INSERT INTO users_sessions VALUES ('a', '$argon2id$v=19$m=65536,t=3,p=4$x$y'), ('b', NULL)")
        )
    return engine


def test_the_upgrade_ends_every_session():
    migration = _migration_module()
    engine = _engine_with_sessions()

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade_session_refresh_token_digest()

    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM users_sessions")).scalar() == 0


def test_the_downgrade_leaves_the_table_alone():
    migration = _migration_module()
    engine = _engine_with_sessions()

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.downgrade_session_refresh_token_digest()

    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM users_sessions")).scalar() == 2
