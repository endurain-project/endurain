"""Garmin Connect activities are stored once against real PostgreSQL.

A Garmin sync carries no explicit ``dedup_key``: ingestion derives ``garmin:<id>:<start>`` from the
activity's provider id. When two syncs of the same activity run at once, on this replica or another,
both pass the read-then-write check, and the unique index on ``(user_id, dedup_key)`` is what holds.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
from tests._helpers.db import ensure_user

_USER_ID = 1
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
def factory(pg_factory):
    ensure_user(pg_factory, _USER_ID)
    return pg_factory


def _garmin_activity(garmin_id: int, start: datetime = _START) -> activity_contracts.ParsedActivity:
    return activity_contracts.ParsedActivity(
        activity=activity_contracts.ActivityCore(
            user_id=_USER_ID,
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


def _store(factory, parsed) -> int:
    with factory() as db:
        stored = activity_integration.store_parsed_activity(parsed, db)
        db.commit()
        return stored.id


def test_concurrent_syncs_of_one_garmin_activity_store_it_once(factory):
    barrier = threading.Barrier(_THREADS)
    ids: list[int] = []
    errors: list[BaseException] = []

    def sync() -> None:
        try:
            barrier.wait()
            ids.append(_store(factory, _garmin_activity(456)))
        except BaseException as err:
            errors.append(err)

    threads = [threading.Thread(target=sync) for _ in range(_THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert len(set(ids)) == 1
    with factory() as db:
        keys = db.scalars(select(activity_models.Activity.dedup_key)).all()
    assert keys == [f"garmin:456:{int(_START.timestamp())}"]


def test_the_activities_of_one_multi_activity_file_are_all_stored(factory):
    first = _store(factory, _garmin_activity(789))
    second = _store(factory, _garmin_activity(789, _START + timedelta(hours=2)))

    assert first != second
