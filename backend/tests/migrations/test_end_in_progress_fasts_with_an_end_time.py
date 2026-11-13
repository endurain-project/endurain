"""Tests for the migration that completes in-progress fasts that have an end time (revision 41)."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/41_end_in_progress_fasts_with_an_end_time.py"
)


def _migration_module():
    """Load the revision as a Python module."""
    spec = importlib.util.spec_from_file_location("end_in_progress_fasts_with_an_end_time", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _at(hour: int, day: int = 15) -> datetime:
    return datetime(2024, 1, day, hour, tzinfo=UTC)


def test_it_chains_onto_the_previous_head() -> None:
    assert _migration_module().down_revision == "c9a3f7b15e42"


def test_upgrade_completes_only_in_progress_fasts_with_an_end_time() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    table = sa.Table(
        "health_fasting",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("status", sa.String, nullable=False),
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
                # Running with an end and a stored duration: both kept.
                {
                    "id": 1,
                    "status": "in_progress",
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(20),
                    "actual_duration_seconds": 999,
                    "version": 1,
                },
                # Running with an end and no duration: derived.
                {
                    "id": 2,
                    "status": "in_progress",
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(10),
                    "actual_duration_seconds": None,
                    "version": 3,
                },
                # Running with an end before its start and no duration: completed, duration left empty.
                {
                    "id": 3,
                    "status": "in_progress",
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(2),
                    "actual_duration_seconds": None,
                    "version": 1,
                },
                # Genuinely running: untouched.
                {
                    "id": 4,
                    "status": "in_progress",
                    "fast_start_time": _at(8),
                    "fast_end_time": None,
                    "actual_duration_seconds": None,
                    "version": 1,
                },
                # Other statuses with an end: untouched.
                {
                    "id": 5,
                    "status": "broken",
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(9),
                    "actual_duration_seconds": 3600,
                    "version": 1,
                },
                {
                    "id": 6,
                    "status": "cancelled",
                    "fast_start_time": _at(8),
                    "fast_end_time": _at(9),
                    "actual_duration_seconds": None,
                    "version": 1,
                },
            ],
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        stored = {
            row.id: (row.status, row.fast_end_time is not None, row.actual_duration_seconds, row.version)
            for row in connection.execute(sa.select(table))
        }
    engine.dispose()

    assert stored == {
        1: ("completed", True, 999, 2),
        2: ("completed", True, 2 * 3600, 4),
        3: ("completed", True, None, 2),
        4: ("in_progress", False, None, 1),
        5: ("broken", True, 3600, 1),
        6: ("cancelled", True, None, 1),
    }


def test_downgrade_changes_nothing() -> None:
    assert _migration_module().downgrade() is None
