"""Overlapping fasts and the health data migrations against real PostgreSQL.

The unit tests run on SQLite, which ignores the PostgreSQL-only partial index and stores no UTC offsets, so
the overlap rule beside the real one-running-fast index, and the migrations over ``timestamptz`` columns,
are checked here.
"""

import threading
import time
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text

import core.date_range as core_date_range
import core.exceptions as core_exceptions
import modules.health.health_fasting.crud as fasting_crud
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
from tests._helpers import alembic_chain
from tests._helpers.db import ensure_user

_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)
_REVISION_39_BEFORE = "7c3e9a1d5b24"
_REVISION_39 = "b6e2d4a8c031"
_REVISION_40 = "c9a3f7b15e42"


def _hours(n: float) -> datetime:
    return _T0 + timedelta(hours=n)


@pytest.fixture
def db(pg_factory):
    ensure_user(pg_factory, _USER_ID)
    with pg_factory() as session:
        yield session


def _fast(db, start, end=None, status="completed"):
    return fasting_service.create_health_fasting(
        _USER_ID, fasting_schema.HealthFastingCreate(fast_start_time=start, fast_end_time=end, status=status), db
    )


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


def test_the_migration_deletes_the_records_before_1900(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_39_BEFORE)
    with upgrade_db.begin() as connection:
        alembic_chain.seed_users(connection)
        connection.execute(
            text("INSERT INTO health_steps (user_id, date, steps, version) VALUES (1, '0001-01-01', 1, 1)")
        )
        connection.execute(
            text("INSERT INTO health_steps (user_id, date, steps, version) VALUES (1, '1900-01-01', 1, 1)")
        )
        connection.execute(
            text("INSERT INTO health_poop (user_id, date_time, version) VALUES (1, '0001-01-01 00:30+00', 1)")
        )
        connection.execute(
            text("INSERT INTO health_poop (user_id, date_time, version) VALUES (1, '2024-01-01 00:30+00', 1)")
        )
        connection.execute(
            text(
                "INSERT INTO health_fasting (user_id, fast_start_time, status, version) "
                "VALUES (1, '1899-12-31 23:00+00', 'cancelled', 1)"
            )
        )

    alembic_chain.upgrade(upgrade_db, _REVISION_39)

    with upgrade_db.connect() as connection:
        assert connection.scalars(text("SELECT date FROM health_steps")).all() == [date(1900, 1, 1)]
        assert connection.scalar(text("SELECT count(*) FROM health_poop")) == 1
        assert connection.scalar(text("SELECT count(*) FROM health_fasting")) == 0


def test_the_migration_derives_durations_from_timestamptz_columns(upgrade_db):
    alembic_chain.upgrade(upgrade_db, _REVISION_39)
    with upgrade_db.begin() as connection:
        alembic_chain.seed_users(connection)
        connection.execute(
            text(
                "INSERT INTO health_fasting "
                "(user_id, fast_start_time, fast_end_time, actual_duration_seconds, status, version) "
                "VALUES (1, '2026-10-01 08:00+02', '2026-10-01 20:00+02', 60, 'completed', 1), "
                "(1, '2026-10-03 08:00+00', '2026-10-03 10:00+00', 7200, 'completed', 1), "
                "(1, '2026-10-05 08:00+00', NULL, NULL, 'cancelled', 1)"
            )
        )

    alembic_chain.upgrade(upgrade_db, _REVISION_40)

    with upgrade_db.connect() as connection:
        rows = connection.execute(
            text("SELECT actual_duration_seconds, version FROM health_fasting ORDER BY fast_start_time")
        ).all()
    assert [tuple(row) for row in rows] == [(12 * 3600, 2), (7200, 1), (None, 1)]


def test_concurrent_overlapping_creates_store_exactly_one(pg_factory, monkeypatch):
    ensure_user(pg_factory, _USER_ID)
    check = fasting_crud.fasting_overlaps

    def slow_check(*args, **kwargs):
        # Widens the window between the check and the insert so an unserialised writer is caught in it.
        result = check(*args, **kwargs)
        time.sleep(0.3)
        return result

    monkeypatch.setattr(fasting_crud, "fasting_overlaps", slow_check)
    attempts = 6
    barrier = threading.Barrier(attempts)
    outcomes: list = []

    def run(offset: float) -> None:
        barrier.wait()
        with pg_factory() as session:
            try:
                outcomes.append(_fast(session, _hours(offset), _hours(offset + 10)))
            except Exception as err:
                session.rollback()
                outcomes.append(err)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    created = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, core_exceptions.ConflictError)]
    assert len(outcomes) == attempts
    assert len(created) == 1
    assert len(refused) == attempts - 1
    assert all("overlaps" in str(error) for error in refused)


def test_the_list_and_count_windows_use_the_users_local_day(db, monkeypatch):
    # 22:00 UTC on 1 October is 08:00 on 2 October in UTC+10.
    _fast(db, datetime(2026, 10, 1, 22, 0, tzinfo=UTC), datetime(2026, 10, 2, 2, 0, tzinfo=UTC))
    monkeypatch.setattr(fasting_service.users_integration, "resolve_timezone", lambda *_: "Australia/Brisbane")
    local_day = date(2026, 10, 2)

    page = fasting_service.list_health_fasting(
        _USER_ID, db, date_range=core_date_range.DateRange(start_date=local_day, end_date=local_day)
    )
    utc_day = date(2026, 10, 1)
    other = fasting_service.list_health_fasting(
        _USER_ID, db, date_range=core_date_range.DateRange(start_date=utc_day, end_date=utc_day)
    )

    assert (page.total, len(page.items)) == (1, 1)
    assert other.total == 0
