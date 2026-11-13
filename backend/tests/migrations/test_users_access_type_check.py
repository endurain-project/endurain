"""Tests for the migration that constrains ``users.access_type`` (revision 84)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/84_users_access_type_check.py"


def _migration_module():
    spec = importlib.util.spec_from_file_location("users_access_type_check", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_revision_follows_migration_83():
    assert _migration_module().down_revision == "a83d7e2c5f19"


def test_the_upgrade_adds_a_check_that_allows_only_the_two_access_types():
    migration = _migration_module()
    with patch.object(migration.op, "create_check_constraint") as create:
        migration.upgrade()

    name, table, condition = create.call_args.args
    assert (name, table) == ("ck_users_access_type", "users")
    assert condition == "access_type IN ('regular', 'admin')"


def test_the_downgrade_drops_the_check():
    migration = _migration_module()
    with patch.object(migration.op, "drop_constraint") as drop:
        migration.downgrade()

    drop.assert_called_once_with("ck_users_access_type", "users", type_="check")


def test_the_model_declares_the_same_check():
    from modules.users.users.models import Users

    names = {c.name: str(c.sqltext) for c in Users.__table__.constraints if c.name}
    assert names["ck_users_access_type"] == "access_type IN ('regular', 'admin')"
