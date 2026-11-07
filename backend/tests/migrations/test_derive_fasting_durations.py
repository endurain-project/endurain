"""Tests for the migration that derives fasting durations from the stored times (revision 40)."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/40_derive_fasting_durations.py"


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("derive_fasting_durations", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _at(hour: int, day: int = 15) -> datetime:
    return datetime(2024, 1, day, hour, tzinfo=UTC)


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "b6e2d4a8c031"


def test_upgrade_recomputes_only_the_durations_that_differ() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "health_fasting",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fast_start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fast_end_time", sa.DateTime(timezone=True)),
        sa.Column("actual_duration_seconds", sa.Integer),
        sa.Column("version", sa.Integer, nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert(),
            [
                # Edited end, duration left as it was.
                {
                    "id": 1,
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(20),
                    "actual_duration_seconds": 3600,
                    "version": 1,
                },
                # Already right.
                {
                    "id": 2,
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(10),
                    "actual_duration_seconds": 7200,
                    "version": 1,
                },
                # Written by the client with no duration at all.
                {
                    "id": 3,
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(9),
                    "actual_duration_seconds": None,
                    "version": 1,
                },
                # No end: nothing to derive.
                {
                    "id": 4,
                    "fast_start_time": _at(8),
                    "fast_end_time": None,
                    "actual_duration_seconds": None,
                    "version": 1,
                },
                # Ends before it starts: left alone.
                {
                    "id": 5,
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(2),
                    "actual_duration_seconds": 500,
                    "version": 1,
                },
            ],
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        stored = {
            row.id: (row.actual_duration_seconds, row.version)
            for row in connection.execute(sa.select(table.c.id, table.c.actual_duration_seconds, table.c.version))
        }
    engine.dispose()

    assert stored == {1: (12 * 3600, 2), 2: (7200, 1), 3: (3600, 2), 4: (None, 1), 5: (500, 1)}


def test_downgrade_changes_nothing() -> None:
    assert _migration_module().downgrade() is None
