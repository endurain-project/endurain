"""Garmin Connect activities are stored once against real PostgreSQL.

A Garmin sync is identified by its provider id and the recording's start. When two syncs of the same activity
run at once, on this replica or another, both pass the read-then-write check, and the unique index on the
provider sources is what holds.
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
from tests._factories.users import make_user

_THREADS = 6
_START = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)


@pytest.fixture
def user_id(committed_sessions) -> uuid.UUID:
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return user.id


def _garmin_activity(user_id: uuid.UUID, garmin_id: int, start: datetime = _START) -> activity_contracts.ParsedActivity:
    return activity_contracts.ParsedActivity(
        activity=activity_contracts.ActivityCore(
            user_id=user_id,
            name="Ride",
            distance=1000,
            activity_type=1,
            start_time=start,
            end_time=start + timedelta(hours=1),
            total_elapsed_time=3600.0,
            total_timer_time=3540.0,
            garminconnect_activity_id=garmin_id,
            **{flag: False for flag in _PRIVACY_FLAGS},
        ),
        components={},
        source=activity_contracts.ImportSource(kind="garmin"),
    )


def _store(sessions, parsed) -> uuid.UUID:
    with sessions() as db:
        stored = activity_integration.store_parsed_activity(parsed, db)
        db.commit()
        return stored.id


def test_concurrent_syncs_of_one_garmin_activity_store_it_once(committed_sessions, user_id):
    barrier = threading.Barrier(_THREADS)
    ids: list[uuid.UUID] = []
    errors: list[BaseException] = []

    def sync() -> None:
        try:
            barrier.wait()
            ids.append(_store(committed_sessions, _garmin_activity(user_id, 456)))
        except BaseException as err:
            errors.append(err)

    threads = [threading.Thread(target=sync) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert len(set(ids)) == 1
    with committed_sessions() as db:
        sources = db.execute(
            select(
                activity_models.ActivitySource.kind,
                activity_models.ActivitySource.provider_id,
                activity_models.ActivitySource.session_start,
            )
        ).all()
    assert [tuple(row) for row in sources] == [("garmin", 456, _START)]


def test_the_activities_of_one_multi_activity_file_are_all_stored(committed_sessions, user_id):
    first = _store(committed_sessions, _garmin_activity(user_id, 789))
    second = _store(committed_sessions, _garmin_activity(user_id, 789, _START + timedelta(hours=2)))

    assert first != second


def test_concurrent_window_syncs_of_one_user_store_each_activity_once(committed_sessions, account, make_linked):
    import modules.garmin.activity_service as garmin_activity_service
    from tests._factories.garmin import rate_limits

    user = make_linked()
    account.add_activity(456, start=_START)
    barrier = threading.Barrier(_THREADS)
    errors: list[BaseException] = []

    def sync() -> None:
        try:
            barrier.wait()
            garmin_activity_service.get_user_garminconnect_activities_by_dates(
                user.id, _START - timedelta(days=1), _START + timedelta(days=1), rate_limits()
            )
        except BaseException as err:
            errors.append(err)

    threads = [threading.Thread(target=sync) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors
    with committed_sessions() as db:
        rows = db.scalars(
            select(activity_models.ActivitySource.provider_id).where(activity_models.ActivitySource.kind == "garmin")
        ).all()
    assert rows == [456]
