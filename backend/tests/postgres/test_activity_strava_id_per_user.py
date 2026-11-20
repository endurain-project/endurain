"""A Strava activity ID is held per user against real PostgreSQL.

Two Endurain accounts may link the same Strava athlete, so each stores that athlete's activities under the same
Strava activity ID. Only ``(user_id, dedup_key)`` holds an activity once for a user.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import ensure_user

_START = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
_STRAVA_ID = 9_000_000_001
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
    for user_id in (MOCK_USER_ID, OTHER_USER_ID):
        ensure_user(pg_factory, user_id)
    return pg_factory


def _strava_activity(user_id: uuid.UUID) -> activity_contracts.ParsedActivity:
    return activity_contracts.ParsedActivity(
        activity=activity_contracts.ActivityCore(
            user_id=user_id,
            name="Ride",
            distance=1000,
            activity_type=1,
            start_time=_START,
            end_time=_START + timedelta(hours=1),
            total_elapsed_time=3600.0,
            total_timer_time=3540.0,
            strava_activity_id=_STRAVA_ID,
            **{flag: False for flag in _PRIVACY_FLAGS},
        ),
        components={},
        source=activity_contracts.ImportSource(kind="strava"),
    )


def _insert_activity(db, user_id: uuid.UUID, strava_id: int, dedup_key: str) -> uuid.UUID:
    activity = activity_models.Activity(
        user_id=user_id,
        distance=1,
        activity_type=1,
        start_time=_START,
        end_time=_START + timedelta(hours=1),
        total_elapsed_time=1,
        total_timer_time=1,
        strava_activity_id=strava_id,
        dedup_key=dedup_key,
        visibility=0,
        created_at=_START,
        **{flag: False for flag in _PRIVACY_FLAGS},
    )
    db.add(activity)
    db.flush()
    return activity.id


def test_two_users_store_the_same_strava_activity(factory):
    with factory() as db:
        first = activity_integration.store_parsed_activity(_strava_activity(MOCK_USER_ID), db)
        second = activity_integration.store_parsed_activity(_strava_activity(OTHER_USER_ID), db)
        db.commit()

    assert first.id != second.id
    with factory() as db:
        owners = db.scalars(
            select(activity_models.Activity.user_id).where(activity_models.Activity.strava_activity_id == _STRAVA_ID)
        ).all()
    assert sorted(owners) == sorted([MOCK_USER_ID, OTHER_USER_ID])
