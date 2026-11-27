"""Tests for the migration that drops the CSRF token hash of a session."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/17_session_digest_and_strava_scope.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("drop_session_csrf_token_hash", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _columns(engine: sa.Engine) -> list[str]:
    return [column["name"] for column in sa.inspect(engine).get_columns("users_sessions")]


def _engine(with_column: bool) -> sa.Engine:
    engine = sa.create_engine("sqlite://")
    column = ", csrf_token_hash VARCHAR(255)" if with_column else ""
    with engine.begin() as connection:
        connection.execute(sa.text(f"CREATE TABLE users_sessions (id VARCHAR(36) PRIMARY KEY{column})"))
    return engine


def test_the_upgrade_drops_the_column():
    migration = _migration_module()
    engine = _engine(with_column=True)

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.upgrade_drop_session_csrf_token_hash()

    assert _columns(engine) == ["id"]


def test_the_downgrade_adds_the_nullable_column_back():
    migration = _migration_module()
    engine = _engine(with_column=False)

    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration.downgrade_drop_session_csrf_token_hash()

    column = next(c for c in sa.inspect(engine).get_columns("users_sessions") if c["name"] == "csrf_token_hash")
    assert column["nullable"] is True
    assert column["type"].length == 255
