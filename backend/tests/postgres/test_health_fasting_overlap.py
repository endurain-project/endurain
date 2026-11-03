"""Overlapping fasts and the health data migrations against real PostgreSQL.

The unit tests run on SQLite, which ignores the PostgreSQL-only partial index and stores no UTC offsets, so
the overlap rule beside the real one-running-fast index, and the migrations over ``timestamptz`` columns,
are checked here.
"""

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

import core.exceptions as core_exceptions
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
from tests._helpers.db import ensure_user

_T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
_VERSIONS = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0"


def _hours(n: float) -> datetime:
    return _T0 + timedelta(hours=n)


@pytest.fixture
def db(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as session:
        yield session


def _fast(db, start, end=None, status="completed"):
    return fasting_service.create_health_fasting(
        1, fasting_schema.HealthFastingCreate(fast_start_time=start, fast_end_time=end, status=status), db
    )


def _run(db, file_name):
    spec = importlib.util.spec_from_file_location(file_name.removesuffix(".py"), _VERSIONS / file_name)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(db.connection())):
        migration.upgrade()
    db.commit()


def test_overlapping_fasts_are_refused_and_touching_ones_are_not(db):
    _fast(db, _hours(0), _hours(10))

    with pytest.raises(core_exceptions.ConflictError):
        _fast(db, _hours(5), _hours(15))
    _fast(db, _hours(10), _hours(12))


def test_a_running_fast_blocks_a_later_completed_one_but_not_an_earlier_one(db):
    _fast(db, _hours(0), _hours(20))
    _fast(db, _hours(20), None, "in_progress")

    with pytest.raises(core_exceptions.ConflictError):
        _fast(db, _hours(30), _hours(40))


def test_the_migration_deletes_the_records_before_1900(db):
    db.execute(text("INSERT INTO health_steps (user_id, date, steps, version) VALUES (1, '0001-01-01', 1, 1)"))
    db.execute(text("INSERT INTO health_steps (user_id, date, steps, version) VALUES (1, '1900-01-01', 1, 1)"))
    db.execute(text("INSERT INTO health_poop (user_id, date_time, version) VALUES (1, '0001-01-01 00:30+00', 1)"))
    db.execute(text("INSERT INTO health_poop (user_id, date_time, version) VALUES (1, '2024-01-01 00:30+00', 1)"))
    db.execute(
        text(
            "INSERT INTO health_fasting (user_id, fast_start_time, status, version) VALUES (1, '1899-12-31 23:00+00', 'cancelled', 1)"
        )
    )
    db.commit()

    _run(db, "39_delete_health_records_before_1900.py")

    assert db.scalars(text("SELECT date FROM health_steps")).all() == [date(1900, 1, 1)]
    assert db.scalar(text("SELECT count(*) FROM health_poop")) == 1
    assert db.scalar(text("SELECT count(*) FROM health_fasting")) == 0


def test_the_migration_derives_durations_from_timestamptz_columns(db):
    db.execute(
        text(
            "INSERT INTO health_fasting (user_id, fast_start_time, fast_end_time, actual_duration_seconds, status, version) "
            "VALUES (1, '2026-10-01 08:00+02', '2026-10-01 20:00+02', 60, 'completed', 1), "
            "(1, '2026-10-03 08:00+00', '2026-10-03 10:00+00', 7200, 'completed', 1), "
            "(1, '2026-10-05 08:00+00', NULL, NULL, 'cancelled', 1)"
        )
    )
    db.commit()

    _run(db, "40_derive_fasting_durations.py")

    rows = db.execute(
        text("SELECT actual_duration_seconds, version FROM health_fasting ORDER BY fast_start_time")
    ).all()
    assert [tuple(row) for row in rows] == [(12 * 3600, 2), (7200, 1), (None, 1)]
