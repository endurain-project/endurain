"""Tests for the per-session identity-provider token migration (revision 48)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/48_idp_session_tokens.py"


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("idp_session_tokens", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_strava_revoked_at_revision() -> None:
    migration = _migration_module()

    assert migration.revision == "c9f2d6a3e851"
    assert migration.down_revision == "b4c8e1f7a362"


def test_upgrade_creates_the_session_table_without_a_session_foreign_key() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "create_index"),
        patch.object(migration.op, "drop_column"),
    ):
        migration.upgrade()

    assert create_table.call_args.args[0] == "idp_session_tokens"
    items = create_table.call_args.args[1:]
    columns = {item.name: item for item in items if hasattr(item, "type")}
    assert set(columns) == {
        "id",
        "session_id",
        "user_id",
        "idp_id",
        "refresh_token",
        "access_token_expires_at",
        "refresh_token_updated_at",
        "created_at",
    }
    assert columns["refresh_token"].nullable is True
    assert all(not columns[name].nullable for name in ("session_id", "user_id", "idp_id", "created_at"))
    foreign_keys = [item for item in items if type(item).__name__ == "ForeignKeyConstraint"]
    assert sorted(fk.elements[0].target_fullname for fk in foreign_keys) == ["identity_providers.id", "users.id"]
    assert all(fk.ondelete == "CASCADE" for fk in foreign_keys)
    table = sa.Table("idp_session_tokens", sa.MetaData(), *items)
    unique = [constraint for constraint in table.constraints if isinstance(constraint, sa.UniqueConstraint)]
    assert [[column.name for column in constraint.columns] for constraint in unique] == [["session_id"]]


def test_upgrade_drops_the_three_link_token_columns() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "create_table"),
        patch.object(migration.op, "create_index"),
        patch.object(migration.op, "drop_column") as drop_column,
    ):
        migration.upgrade()

    assert sorted(call.args for call in drop_column.call_args_list) == sorted(
        ("users_identity_providers", name)
        for name in ("idp_refresh_token", "idp_access_token_expires_at", "idp_refresh_token_updated_at")
    )


def test_downgrade_restores_the_empty_columns_and_drops_the_table() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "drop_index"),
        patch.object(migration.op, "drop_table") as drop_table,
    ):
        migration.downgrade()

    restored = {call.args[1].name: call.args[1] for call in add_column.call_args_list}
    assert set(restored) == {"idp_refresh_token", "idp_access_token_expires_at", "idp_refresh_token_updated_at"}
    assert all(column.nullable for column in restored.values())
    assert all(call.args[0] == "users_identity_providers" for call in add_column.call_args_list)
    drop_table.assert_called_once_with("idp_session_tokens")
