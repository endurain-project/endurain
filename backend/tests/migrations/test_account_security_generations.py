"""Tests for the account security generations migration (revision 67)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/67_account_security_generations.py"
)


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("account_security_generations", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "c91ac2dad0f0"


def test_upgrade_creates_the_table_keyed_by_a_cascading_user_id() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "create_table") as create_table,
        patch.object(migration.op, "add_column"),
        patch.object(migration.op, "alter_column"),
    ):
        migration.upgrade()

    assert create_table.call_args.args[0] == "account_security_generations"
    items = create_table.call_args.args[1:]
    columns = {item.name: item for item in items if hasattr(item, "type")}
    assert set(columns) == {"user_id", "generation", "updated_at"}
    assert all(not column.nullable for column in columns.values())
    assert columns["updated_at"].type.timezone
    assert str(columns["generation"].server_default.arg) == "0"
    foreign_key = next(item for item in items if type(item).__name__ == "ForeignKeyConstraint")
    assert foreign_key.ondelete == "CASCADE"
    assert any(type(item).__name__ == "PrimaryKeyConstraint" for item in items)


def test_upgrade_adds_a_nullable_generation_to_oauth_states() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "create_table"),
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "alter_column"),
    ):
        migration.upgrade()

    table, column = add_column.call_args_list[0].args
    assert table == "oauth_states"
    assert column.name == "security_generation"
    assert column.nullable


def test_upgrade_adds_ends_other_sessions_defaulting_to_false() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "create_table"),
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "alter_column"),
    ):
        migration.upgrade()

    table, column = add_column.call_args_list[1].args
    assert table == "oauth_states"
    assert column.name == "ends_other_sessions"
    assert not column.nullable
    assert str(column.server_default.arg) == "false"


def test_upgrade_rewords_the_session_id_comment_to_the_session_that_started_the_flow() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "create_table"),
        patch.object(migration.op, "add_column"),
        patch.object(migration.op, "alter_column") as alter_column,
    ):
        migration.upgrade()

    assert alter_column.call_args.args == ("oauth_states", "session_id")
    assert alter_column.call_args.kwargs["comment"] == "Session that started a link or step-up flow"


def test_downgrade_drops_the_columns_and_the_table() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "drop_table") as drop_table,
        patch.object(migration.op, "drop_column") as drop_column,
        patch.object(migration.op, "alter_column") as alter_column,
    ):
        migration.downgrade()

    assert [call.args for call in drop_column.call_args_list] == [
        ("oauth_states", "ends_other_sessions"),
        ("oauth_states", "security_generation"),
    ]
    assert alter_column.call_args.kwargs["existing_comment"] == "Session that started a link or step-up flow"
    drop_table.assert_called_once_with("account_security_generations")
