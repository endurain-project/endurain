"""Activities and the rows that hang off one, as the application stores them, for tests on the real database."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud

#: The start of an activity made without one.
DEFAULT_START = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)


def make_activity(
    db: Session,
    user_id: uuid.UUID,
    *,
    visibility: activity_constants.ActivityVisibility = activity_constants.ActivityVisibility.PRIVATE,
    **overrides: object,
) -> activity_schema.ActivityRead:
    """Stage an activity through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The activity's owner.
        visibility: Who may see the activity; private by default, as for a new account.
        **overrides: Field values of :class:`~modules.activities.activity.contracts.ActivityCore`, which replace the
            defaults of a one-hour, 10 km run starting at :data:`DEFAULT_START` with nothing hidden.

    Returns:
        The staged activity.
    """
    values: dict[str, object] = {
        "user_id": user_id,
        "name": "Morning run",
        "distance": 10000,
        "activity_type": activity_constants.ActivityType.RUN.stored,
        "start_time": DEFAULT_START,
        "end_time": DEFAULT_START.replace(hour=9),
        "timezone": "UTC",
        "total_elapsed_time": 3600.0,
        "total_timer_time": 3600.0,
        "visibility": visibility.stored,
        "is_hidden": False,
        "hide_start_time": False,
        "hide_location": False,
        "hide_map": False,
        "hide_hr": False,
        "hide_power": False,
        "hide_cadence": False,
        "hide_elevation": False,
        "hide_speed": False,
        "hide_pace": False,
        "hide_laps": False,
        "hide_workout_sets_steps": False,
        "hide_gear": False,
    }
    values.update(overrides)
    return activity_crud.create_activity(activity_contracts.ActivityCore.model_validate(values), db)


def make_activity_children(db: Session, activity: activity_schema.ActivityRead) -> None:
    """Stage one lap, one set, one workout step and one heart-rate stream for an activity (flushed, not committed).

    Args:
        db: Database session.
        activity: The parent activity.
    """
    activity_laps_crud.create_activity_laps([{"start_time": DEFAULT_START}], activity.id, db)
    activity_sets_crud.create_activity_sets(
        [
            activity_sets_contracts.ActivitySetsCreate(
                activity_id=activity.id, start_time=DEFAULT_START.isoformat(), duration=30.0, set_type="active"
            )
        ],
        activity.id,
        db,
    )
    activity_workout_steps_crud.create_activity_workout_steps(
        [activity_workout_steps_contracts.ActivityWorkoutStepsCreate(message_index=0, duration_type="time")],
        activity.id,
        db,
    )
    activity_streams_crud.create_activity_streams(
        [
            activity_streams_contracts.ActivityStreamsCreate(
                activity_id=activity.id,
                stream_type=activity_streams_constants.STREAM_TYPE_HR,
                stream_waypoints=[{"time": "2025-03-10T08:00:00", "hr": 120}],
            )
        ],
        activity,
        db,
    )


def make_activity_media(
    db: Session, activity: activity_schema.ActivityRead, media_key: str
) -> activity_media_contracts.ActivityMediaRecord:
    """Stage a media record for an activity (flushed, not committed); no blob is stored.

    Args:
        db: Database session.
        activity: The parent activity.
        media_key: The storage key the record names.

    Returns:
        The staged record.
    """
    return activity_media_crud.create_activity_media(activity.id, media_key, db)
