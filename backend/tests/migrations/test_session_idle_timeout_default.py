"""Tests for the migration that turns the session idle timeout on for new installs (revision 65)."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/65_session_idle_timeout_default.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("session_idle_timeout_default", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        conn.execute(
            sa.text(
                "CREATE TABLE server_settings (id INTEGER PRIMARY KEY, session_idle_timeout_enabled BOOLEAN NOT NULL, "
                "session_idle_timeout_hours INTEGER NOT NULL)"
            )
        )
        yield conn


def _run(connection, step: str, enabled: bool, hours: int, users: int = 0) -> tuple[bool, int]:
    connection.execute(sa.text("DELETE FROM server_settings"))
    connection.execute(sa.text("DELETE FROM users"))
    connection.execute(
        sa.text("INSERT INTO server_settings VALUES (1, :enabled, :hours)"), {"enabled": enabled, "hours": hours}
    )
    for user_id in range(1, users + 1):
        connection.execute(sa.text("INSERT INTO users (id) VALUES (:id)"), {"id": user_id})
    migration = _migration_module()
    with Operations.context(MigrationContext.configure(connection)):
        getattr(migration, step)()
    row = connection.execute(
        sa.text("SELECT session_idle_timeout_enabled, session_idle_timeout_hours FROM server_settings WHERE id = 1")
    ).one()
    return bool(row[0]), row[1]


def test_the_revision_follows_migration_64():
    migration = _migration_module()
    assert (migration.revision, migration.down_revision) == ("e65a3c4d5f6b", "d64f2b3c4e5a")


def test_the_upgrade_turns_the_timeout_on_when_no_account_exists(connection):
    assert _run(connection, "upgrade", False, 1) == (True, 72)


def test_the_upgrade_keeps_the_setting_when_an_account_exists(connection):
    assert _run(connection, "upgrade", False, 1, users=1) == (False, 1)


@pytest.mark.parametrize(("enabled", "hours"), [(False, 5), (True, 1), (True, 5), (False, 72)])
def test_the_upgrade_keeps_a_setting_that_is_not_the_shipped_value(connection, enabled, hours):
    assert _run(connection, "upgrade", enabled, hours) == (enabled, hours)


def test_the_downgrade_reverts_the_values_this_migration_set(connection):
    assert _run(connection, "downgrade", True, 72) == (False, 1)


@pytest.mark.parametrize(("enabled", "hours"), [(True, 5), (False, 72), (False, 1)])
def test_the_downgrade_keeps_a_setting_an_administrator_changed(connection, enabled, hours):
    assert _run(connection, "downgrade", enabled, hours) == (enabled, hours)
