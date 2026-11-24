"""Overlapping fasts, on the real database.

The overlap rule reads the user's fasts and the writer stores afterwards, so the writers of one user are serialised by
an advisory lock; the one-running-fast index is covered in ``test_one_running_fast``.
"""

import threading
from datetime import UTC, date, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.date_range as core_date_range
import core.exceptions as core_exceptions
import modules.health.health_fasting.models as fasting_models
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
from tests._factories.users import make_user

_T0 = datetime(2026, 10, 1, 8, 0, tzinfo=UTC)


def _hours(n: float) -> datetime:
    return _T0 + timedelta(hours=n)


@pytest.fixture
def user(db):
    return make_user(db)


def _fast(db, user, start, end=None, status="completed"):
    return fasting_service.create_health_fasting(
        user.id, fasting_schema.HealthFastingCreate(fast_start_time=start, fast_end_time=end, status=status), db
    )


def _count(factory) -> int:
    with factory() as db:
        return db.scalar(sa.select(sa.func.count()).select_from(fasting_models.HealthFasting))


def _wait_until_a_session_waits_for_a_lock(factory, timeout: float = 10.0) -> None:
    """Block until another session of this database waits on a lock, so a test acts at that exact point."""
    deadline = datetime.now(UTC) + timedelta(seconds=timeout)
    with factory() as probe:
        while datetime.now(UTC) < deadline:
            waiting = probe.scalar(
                sa.text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            if waiting:
                return
            # PostgreSQL reads pg_stat_activity once per transaction, so each poll needs a transaction of its own.
            probe.rollback()
            threading.Event().wait(0.02)
    raise AssertionError("no session waited for a lock")


def test_overlapping_fasts_are_refused_and_touching_ones_are_not(db, user):
    _fast(db, user, _hours(0), _hours(10))

    with pytest.raises(core_exceptions.ConflictError, match="overlaps"):
        _fast(db, user, _hours(5), _hours(15))


def test_a_fast_that_starts_where_another_ends_is_accepted(db, user):
    _fast(db, user, _hours(0), _hours(10))

    assert _fast(db, user, _hours(10), _hours(12)).fast_start_time == _hours(10)


def test_another_users_fast_never_overlaps(db, user):
    _fast(db, user, _hours(0), _hours(10))
    other = make_user(db)

    assert _fast(db, other, _hours(5), _hours(15)).user_id == other.id


def test_a_running_fast_blocks_a_later_completed_one_but_not_an_earlier_one(db, user):
    _fast(db, user, _hours(0), _hours(20))
    _fast(db, user, _hours(20), None, "in_progress")

    with pytest.raises(core_exceptions.ConflictError):
        _fast(db, user, _hours(30), _hours(40))


def test_a_writer_waits_for_the_one_holding_the_users_fasting_lock_and_then_sees_its_fast(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    outcome: list = []

    def create_overlapping() -> None:
        with committed_sessions() as db:
            try:
                outcome.append(_fast(db, user, _hours(5), _hours(15)))
            except Exception as err:
                db.rollback()
                outcome.append(err)

    with committed_sessions() as holder:
        fasting_service.stage_import_health_fasting(
            user.id,
            fasting_schema.HealthFastingImport(fast_start_time=_hours(0), fast_end_time=_hours(10), status="completed"),
            holder,
        )
        writer = threading.Thread(target=create_overlapping)
        writer.start()
        _wait_until_a_session_waits_for_a_lock(committed_sessions)
        holder.commit()
    writer.join(timeout=20)

    assert len(outcome) == 1
    assert isinstance(outcome[0], core_exceptions.ConflictError)
    assert "overlaps" in str(outcome[0])
    assert _count(committed_sessions) == 1


def test_concurrent_overlapping_creates_store_exactly_one(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    attempts = 6
    barrier = threading.Barrier(attempts)
    outcomes: list = []

    def run(offset: float) -> None:
        barrier.wait()
        with committed_sessions() as session:
            try:
                outcomes.append(_fast(session, user, _hours(offset), _hours(offset + 10)))
            except Exception as err:
                session.rollback()
                outcomes.append(err)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(attempts)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    refused = [outcome for outcome in outcomes if isinstance(outcome, core_exceptions.ConflictError)]
    assert len(outcomes) == attempts
    assert len(refused) == attempts - 1
    assert all("overlaps" in str(error) for error in refused)
    assert _count(committed_sessions) == 1


def test_the_list_and_count_windows_use_the_users_local_day(db):
    brisbane = make_user(db, timezone="Australia/Brisbane")
    # 22:00 UTC on 1 October is 08:00 on 2 October in UTC+10.
    _fast(db, brisbane, datetime(2026, 10, 1, 22, 0, tzinfo=UTC), datetime(2026, 10, 2, 2, 0, tzinfo=UTC))
    local_day = date(2026, 10, 2)
    utc_day = date(2026, 10, 1)

    page = fasting_service.list_health_fasting(
        brisbane.id, db, date_range=core_date_range.DateRange(start_date=local_day, end_date=local_day)
    )
    other = fasting_service.list_health_fasting(
        brisbane.id, db, date_range=core_date_range.DateRange(start_date=utc_day, end_date=utc_day)
    )

    assert (page.total, len(page.items)) == (1, 1)
    assert other.total == 0
