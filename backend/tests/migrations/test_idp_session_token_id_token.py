"""Tests for the migration that adds the encrypted ID token to ``idp_session_tokens`` (revision 56)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/7_credentials_sessions_and_cadence.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("idp_session_token_id_token", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_adds_a_nullable_text_column_so_existing_sessions_hold_no_id_token():
    migration = _migration_module()
    with patch.object(migration.op, "add_column") as add_column:
        migration.upgrade_idp_session_token_id_token()

    table, column = add_column.call_args.args
    assert (table, column.name, column.nullable) == ("idp_session_tokens", "id_token", True)
    assert isinstance(column.type, sa.Text)


def test_the_downgrade_drops_the_column():
    migration = _migration_module()
    with patch.object(migration.op, "drop_column") as drop_column:
        migration.downgrade_idp_session_token_id_token()

    drop_column.assert_called_once_with("idp_session_tokens", "id_token")
