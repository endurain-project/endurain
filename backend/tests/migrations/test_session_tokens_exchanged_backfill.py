"""Tests for the migration that marks sessions already holding a refresh token as exchanged (revision 49)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/49_session_tokens_exchanged_backfill.py"
)


def _migration_module():
    spec = importlib.util.spec_from_file_location("session_tokens_exchanged_backfill", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_upgrade_marks_only_sessions_with_a_refresh_token_as_exchanged():
    migration = _migration_module()
    with patch.object(migration.op, "execute") as execute:
        migration.upgrade()

    statement = str(execute.call_args.args[0])
    assert "SET tokens_exchanged = true" in statement
    assert "refresh_token IS NOT NULL" in statement
    assert "tokens_exchanged = false" in statement


def test_the_downgrade_changes_nothing():
    migration = _migration_module()
    with patch.object(migration.op, "execute") as execute:
        migration.downgrade()

    execute.assert_not_called()
