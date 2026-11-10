"""Tests for the migration that records the native app a session was handed to (75)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/75_session_app_redirect_uri.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("session_app_redirect_uri", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_rotated_tokens_replacement_index_revision():
    migration = _migration_module()

    assert migration.down_revision == "d74b8f2c6a13"


def test_the_upgrade_adds_a_nullable_column_and_the_downgrade_drops_it():
    migration = _migration_module()
    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "drop_column") as drop_column,
    ):
        migration.upgrade()
        migration.downgrade()

    table, column = add_column.call_args.args
    assert table == "users_sessions"
    assert column.name == "app_redirect_uri"
    assert column.nullable is True
    assert isinstance(column.type, sa.String) and column.type.length == 500
    drop_column.assert_called_once_with("users_sessions", "app_redirect_uri")
