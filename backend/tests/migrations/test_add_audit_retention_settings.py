"""Tests for the audit retention settings migration (revision 37)."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/37_add_audit_retention_settings.py"
)


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("add_audit_retention_settings", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_condition() -> str:
    """Return the check constraint condition the upgrade creates."""
    migration = _migration_module()
    with (
        patch.object(migration.op, "add_column"),
        patch.object(migration.op, "create_check_constraint") as create_check_constraint,
    ):
        migration.upgrade()
    name, table, condition = create_check_constraint.call_args.args
    assert (name, table) == ("audit_retention_days_check", "server_settings")
    return condition


def _condition_holds(condition: str, days: int) -> bool:
    """Store one value in a table that carries the constraint condition, and report whether it was accepted."""
    metadata = sa.MetaData()
    table = sa.Table(
        "server_settings",
        metadata,
        sa.Column("audit_retention_days", sa.Integer, nullable=False),
        sa.CheckConstraint(condition, name="audit_retention_days_check"),
    )
    engine = sa.create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(table.insert().values(audit_retention_days=days))
    except sa.exc.IntegrityError:
        return False
    finally:
        engine.dispose()
    return True


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "d0aa98611b9c"


def test_upgrade_adds_both_columns_not_null_with_their_defaults() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "add_column") as add_column,
        patch.object(migration.op, "create_check_constraint"),
    ):
        migration.upgrade()

    columns = {call.args[1].name: call.args[1] for call in add_column.call_args_list}
    assert {call.args[0] for call in add_column.call_args_list} == {"server_settings"}
    assert set(columns) == {"audit_retention_days", "audit_legal_hold"}
    assert isinstance(columns["audit_retention_days"].type, sa.Integer)
    assert isinstance(columns["audit_legal_hold"].type, sa.Boolean)
    assert not columns["audit_retention_days"].nullable
    assert not columns["audit_legal_hold"].nullable
    assert str(columns["audit_retention_days"].server_default.arg) == "90"
    assert str(columns["audit_legal_hold"].server_default.arg) == "false"


@pytest.mark.parametrize("days", [0, 30, 365, 36500])
def test_the_constraint_accepts_zero_or_the_floor_to_the_maximum(days: int) -> None:
    assert _condition_holds(_check_condition(), days)


@pytest.mark.parametrize("days", [-1, 1, 29, 36501])
def test_the_constraint_refuses_anything_else(days: int) -> None:
    assert not _condition_holds(_check_condition(), days)


def test_downgrade_drops_the_constraint_and_both_columns() -> None:
    migration = _migration_module()

    with (
        patch.object(migration.op, "drop_constraint") as drop_constraint,
        patch.object(migration.op, "drop_column") as drop_column,
    ):
        migration.downgrade()

    drop_constraint.assert_called_once_with("audit_retention_days_check", "server_settings", type_="check")
    assert {call.args for call in drop_column.call_args_list} == {
        ("server_settings", "audit_retention_days"),
        ("server_settings", "audit_legal_hold"),
    }
