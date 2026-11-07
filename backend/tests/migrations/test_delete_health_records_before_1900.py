"""Tests for the migration that deletes health records dated before 1900 (revision 39)."""

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/39_delete_health_records_before_1900.py"
)


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("delete_health_records_before_1900", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table(metadata: sa.MetaData, name: str, column: str, column_type: sa.types.TypeEngine) -> sa.Table:
    return sa.Table(name, metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column(column, column_type))


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "7c3e9a1d5b24"


def test_upgrade_deletes_only_the_records_dated_before_1900() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    dated = {
        "health_steps": ("date", sa.Date(), date(1899, 12, 31), date(1900, 1, 1)),
        "health_water": ("date", sa.Date(), date(1, 1, 1), date(2024, 5, 1)),
        "health_weight": ("date", sa.Date(), date(1000, 6, 1), date(1900, 1, 1)),
        "health_sleep": ("date", sa.Date(), date(1899, 1, 1), date(2024, 5, 1)),
        "health_poop": (
            "date_time",
            sa.DateTime(timezone=True),
            datetime(1899, 12, 31, 23, tzinfo=UTC),
            datetime(1900, 1, 1, tzinfo=UTC),
        ),
        "health_fasting": (
            "fast_start_time",
            sa.DateTime(timezone=True),
            datetime(1, 1, 1, tzinfo=UTC),
            datetime(2024, 5, 1, tzinfo=UTC),
        ),
    }
    tables = {name: _table(metadata, name, column, kind) for name, (column, kind, _, _) in dated.items()}
    metadata.create_all(engine)
    with engine.begin() as connection:
        for name, (column, _, invalid, valid) in dated.items():
            connection.execute(tables[name].insert(), [{"id": 1, column: invalid}, {"id": 2, column: valid}])
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        remaining = {
            name: [row[0] for row in connection.execute(sa.select(table.c.id))] for name, table in tables.items()
        }
    engine.dispose()

    assert remaining == {name: [2] for name in dated}


def test_downgrade_changes_nothing() -> None:
    assert _migration_module().downgrade() is None
