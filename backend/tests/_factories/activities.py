"""Activities and the rows that hang off one, as the application stores them, for tests on the real database."""

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
from sqlalchemy import update
from sqlalchemy.orm import Session

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_exercise_titles.crud as activity_exercise_titles_crud
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_media.contracts as activity_media_contracts
import modules.activities.activity_media.crud as activity_media_crud
import modules.activities.activity_media.service as activity_media_service
import modules.activities.activity_sets.contracts as activity_sets_contracts
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

#: The start of an activity made without one.
DEFAULT_START = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)


def make_activity(
    db: Session,
    user_id: uuid.UUID,
    *,
    visibility: activity_constants.ActivityVisibility = activity_constants.ActivityVisibility.PRIVATE,
    parent_activity_id: uuid.UUID | None = None,
    **overrides: object,
) -> activity_schema.ActivityRead:
    """Stage an activity through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The activity's owner.
        visibility: Who may see the activity; private by default, as for a new account.
        parent_activity_id: The multisport activity the new activity is a leg of, when it is one.
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
    return activity_crud.create_activity(
        activity_contracts.ActivityCore.model_validate(values), db, parent_activity_id=parent_activity_id
    )


#: The legs of a triathlon as ``make_multisport`` lays them out: swim, transition, bike, transition, run.
TRIATHLON_LEGS: tuple[dict[str, object], ...] = (
    {"activity_type": activity_constants.ActivityType.OPEN_WATER_SWIMMING.stored, "distance": 1500, "minutes": 30},
    {"activity_type": activity_constants.ActivityType.TRANSITION.stored, "distance": 0, "minutes": 5},
    {"activity_type": activity_constants.ActivityType.RIDE.stored, "distance": 40000, "minutes": 60},
    {"activity_type": activity_constants.ActivityType.TRANSITION.stored, "distance": 0, "minutes": 3},
    {"activity_type": activity_constants.ActivityType.RUN.stored, "distance": 10000, "minutes": 45},
)


def make_multisport(
    db: Session,
    user_id: uuid.UUID,
    *,
    start: datetime = DEFAULT_START,
    legs: Sequence[Mapping[str, object]] = TRIATHLON_LEGS,
    **overrides: object,
) -> tuple[activity_schema.ActivityRead, list[activity_schema.ActivityRead]]:
    """Stage a multisport activity and its legs, back to back from ``start`` (flushed, not committed).

    The parent carries the sums of its legs, as a multisport file reports them.

    Args:
        db: Database session.
        user_id: The activities' owner.
        start: Where the first leg and the parent start.
        legs: One mapping per leg: ``activity_type``, ``distance`` and ``minutes`` of duration, and any other
            field of :func:`make_activity` (``calories``, ``elevation_gain``, ``gear_id`` ...) to set on the leg.
        **overrides: Field values as for :func:`make_activity`, set on the parent and on every leg.

    Returns:
        The parent and its legs, in order.
    """
    durations = [timedelta(minutes=int(str(leg["minutes"]))) for leg in legs]
    parent = make_activity(
        db,
        user_id,
        name="Triathlon",
        activity_type=activity_constants.ActivityType.MULTISPORT.stored,
        distance=sum(int(str(leg["distance"])) for leg in legs),
        start_time=start,
        end_time=start + sum(durations, timedelta()),
        total_elapsed_time=sum(duration.total_seconds() for duration in durations),
        total_timer_time=sum(duration.total_seconds() for duration in durations),
        **overrides,
    )
    leg_start = start
    stored: list[activity_schema.ActivityRead] = []
    for leg, duration in zip(legs, durations, strict=True):
        fields = {name: value for name, value in leg.items() if name != "minutes"}
        stored.append(
            make_activity(
                db,
                user_id,
                parent_activity_id=parent.id,
                start_time=leg_start,
                end_time=leg_start + duration,
                total_elapsed_time=duration.total_seconds(),
                total_timer_time=duration.total_seconds(),
                **{**overrides, **fields},
            )
        )
        leg_start += duration
    return parent, stored


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


def make_activity_at(
    db: Session,
    user_id: uuid.UUID,
    start: datetime,
    *,
    duration: timedelta = timedelta(hours=1),
    **overrides: object,
) -> activity_schema.ActivityRead:
    """Stage an activity that starts at a chosen instant (flushed, not committed).

    Args:
        db: Database session.
        user_id: The activity's owner.
        start: The start instant; the end follows it by ``duration``.
        duration: How long the activity lasts.
        **overrides: Field values as for :func:`make_activity`.

    Returns:
        The staged activity.
    """
    return make_activity(db, user_id, start_time=start, end_time=start + duration, **overrides)


def set_activity_created_at(db: Session, activity_id: uuid.UUID, created_at: datetime) -> None:
    """Move an activity's creation time (flushed, not committed), which the database stamps with the transaction start.

    Args:
        db: Database session.
        activity_id: The activity to change.
        created_at: When the activity was recorded.
    """
    db.execute(
        update(activity_models.Activity).where(activity_models.Activity.id == activity_id).values(created_at=created_at)
    )
    db.flush()


def make_laps(
    db: Session, activity: activity_schema.ActivityRead, laps: Sequence[Mapping[str, object]]
) -> list[activity_laps_schema.ActivityLapsRead]:
    """Stage laps for an activity through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        activity: The parent activity.
        laps: One mapping of lap fields per lap; a missing field is stored as null.

    Returns:
        The activity's laps as stored, in recorded order.
    """
    activity_laps_crud.create_activity_laps(laps, activity.id, db)
    return activity_laps_crud.get_activity_laps(activity.id, db)


def make_sets(
    db: Session, activity: activity_schema.ActivityRead, sets: Sequence[Mapping[str, object]]
) -> list[activity_sets_schema.ActivitySetsRead]:
    """Stage workout sets for an activity through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        activity: The parent activity.
        sets: One mapping per set with the fields of ``ActivitySetsCreate`` except ``activity_id``.

    Returns:
        The activity's sets as stored, in recorded order.
    """
    activity_sets_crud.create_activity_sets(
        [activity_sets_contracts.ActivitySetsCreate(activity_id=activity.id, **values) for values in sets],
        activity.id,
        db,
    )
    return activity_sets_crud.get_activity_sets(activity.id, db)


def make_workout_steps(
    db: Session, activity: activity_schema.ActivityRead, steps: Sequence[Mapping[str, object]]
) -> list[activity_workout_steps_schema.ActivityWorkoutStepsRead]:
    """Stage workout steps for an activity through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        activity: The parent activity.
        steps: One mapping per step with the fields of ``ActivityWorkoutStepsCreate``.

    Returns:
        The activity's steps as stored, in message-index order.
    """
    activity_workout_steps_crud.create_activity_workout_steps(
        [activity_workout_steps_contracts.ActivityWorkoutStepsCreate(**values) for values in steps],
        activity.id,
        db,
    )
    return activity_workout_steps_crud.get_activity_workout_steps(activity.id, db)


def make_stream(
    db: Session,
    activity: activity_schema.ActivityRead,
    stream_type: int,
    waypoints: Sequence[Mapping[str, object]],
) -> activity_streams_schema.ActivityStreamsRead:
    """Stage one stream for an activity through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        activity: The parent activity.
        stream_type: The stored stream type code.
        waypoints: The stream's samples.

    Returns:
        The stream as stored.
    """
    activity_streams_crud.create_activity_streams(
        [
            activity_streams_contracts.ActivityStreamsCreate(
                activity_id=activity.id, stream_type=stream_type, stream_waypoints=[dict(w) for w in waypoints]
            )
        ],
        activity,
        db,
    )
    stored = activity_streams_crud.get_activity_stream_by_type(activity.id, stream_type, db)
    assert stored is not None
    return stored


def make_exercise_titles(db: Session, titles: Sequence[tuple[int, int, str]]) -> None:
    """Stage exercise titles through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        titles: ``(exercise_category, exercise_name, wkt_step_name)`` triples.
    """
    activity_exercise_titles_crud.create_activity_exercise_titles(
        [
            activity_exercise_titles_contracts.ActivityExerciseTitlesCreate(
                exercise_category=category, exercise_name=name, wkt_step_name=step_name
            )
            for category, name, step_name in titles
        ],
        db,
    )
    db.flush()


def make_stored_media(
    db: Session, activity: activity_schema.ActivityRead, data: bytes, filename: str = "photo.jpg"
) -> activity_media_contracts.ActivityMediaRecord:
    """Store an image for an activity through the media service, blob and row (committed, as the service commits).

    The blob goes to the active platform's storage.

    Args:
        db: Database session.
        activity: The parent activity.
        data: The image bytes.
        filename: The uploaded file name, which fixes the stored extension.

    Returns:
        The stored media record.
    """
    return activity_media_service.store_activity_media_bytes(
        activity.id, filename, data, platform_runtime.get_active_platform().storage, db
    )


def make_parsed_activity(
    user_id: uuid.UUID,
    *,
    components: dict[str, object] | None = None,
    source: activity_contracts.ImportSource | None = None,
    start: datetime = DEFAULT_START,
    **overrides: object,
) -> activity_contracts.ParsedActivity:
    """Build the parsed activity an ingestion source hands to the core (nothing is stored).

    Args:
        user_id: The activity's owner.
        components: Parsed child data keyed by contributor key.
        source: Where the activity came from.
        start: The start instant; the end follows it by an hour.
        **overrides: Field values of :class:`~modules.activities.activity.contracts.ActivityCore`, which replace the
            defaults of a one-hour, 1 km ride with nothing hidden.

    Returns:
        The parsed activity.
    """
    values: dict[str, object] = {
        "user_id": user_id,
        "name": "Imported ride",
        "distance": 1000,
        "activity_type": activity_constants.ActivityType.RIDE.stored,
        "start_time": start,
        "end_time": start + timedelta(hours=1),
        "total_elapsed_time": 3600.0,
        "total_timer_time": 3540.0,
        **{name: False for name in activity_schema.ActivityBase.model_fields if name.startswith("hide_")},
    }
    values.update(overrides)
    return activity_contracts.ParsedActivity(
        activity=activity_contracts.ActivityCore.model_validate(values),
        components=components or {},
        source=source,
    )
