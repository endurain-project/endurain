"""Tests for the migration that records each session's client type and ends the sessions open before it (58)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa

import modules.auth.constants as auth_constants

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/58_session_client_type.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("session_client_type", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def connection():
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text("PRAGMA foreign_keys = ON"))
        conn.execute(
            sa.text("CREATE TABLE users_sessions (id VARCHAR(36) PRIMARY KEY, token_family_id VARCHAR(36) UNIQUE)")
        )
        conn.execute(
            sa.text(
                "CREATE TABLE rotated_refresh_tokens (id INTEGER PRIMARY KEY, token_family_id VARCHAR(36) "
                "REFERENCES users_sessions (token_family_id) ON DELETE CASCADE)"
            )
        )
        conn.execute(sa.text("INSERT INTO users_sessions (id, token_family_id) VALUES ('a', 'fa'), ('b', 'fb')"))
        conn.execute(sa.text("INSERT INTO rotated_refresh_tokens (id, token_family_id) VALUES (1, 'fa')"))
        yield conn
    engine.dispose()


def test_it_has_its_revision_and_chains_onto_the_provider_flags_revision():
    migration = _migration_module()

    assert migration.revision == "a10c7e3f5d21"
    assert migration.down_revision == "c8e2a5f19b36"


def test_the_upgrade_ends_every_session_and_their_rotated_refresh_tokens(connection):
    migration = _migration_module()
    with (
        patch.object(
            migration.op, "execute", side_effect=lambda statement: connection.execute(sa.text(str(statement)))
        ),
        patch.object(migration.op, "add_column"),
        patch.object(migration.op, "create_check_constraint"),
    ):
        migration.upgrade()

    assert connection.execute(sa.text("SELECT count(*) FROM users_sessions")).scalar_one() == 0
    assert connection.execute(sa.text("SELECT count(*) FROM rotated_refresh_tokens")).scalar_one() == 0


def test_the_sessions_end_before_the_non_null_column_is_added():
    migration = _migration_module()
    calls = []
    with (
        patch.object(migration.op, "execute", side_effect=lambda *_: calls.append("execute")),
        patch.object(migration.op, "add_column", side_effect=lambda *_: calls.append("add_column")),
        patch.object(migration.op, "create_check_constraint", side_effect=lambda *_: calls.append("check")),
    ):
        migration.upgrade()

    assert calls == ["execute", "add_column", "check"]


def test_the_upgrade_adds_a_non_null_client_type_limited_to_the_client_types():
    migration = _migration_module()
    with (
        patch.object(migration.op, "execute") as execute,
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "create_check_constraint") as create_check,
    ):
        migration.upgrade()

    assert str(execute.call_args.args[0]) == "DELETE FROM users_sessions"
    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable, column.server_default) == (
        "users_sessions",
        "client_type",
        False,
        None,
    )
    name, check_table, condition = create_check.call_args.args
    assert (name, check_table) == ("ck_users_sessions_client_type", "users_sessions")
    assert condition == "client_type IN ({})".format(", ".join(f"'{c.value}'" for c in auth_constants.ClientType))


def test_the_downgrade_drops_the_check_and_the_column():
    migration = _migration_module()
    with (
        patch.object(migration.op, "drop_constraint") as drop_constraint,
        patch.object(migration.op, "drop_column") as drop_column,
    ):
        migration.downgrade()

    drop_constraint.assert_called_once_with("ck_users_sessions_client_type", "users_sessions", type_="check")
    drop_column.assert_called_once_with("users_sessions", "client_type")
