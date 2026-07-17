"""Core activity ingestion — persist a canonical :class:`ParsedActivity`.

This is the seam that makes parsing irrelevant to the activities core (plan §5):
it accepts a format-agnostic :class:`~modules.activities.activity.schema.ParsedActivity`
and persists the activity plus its streams/laps/sets/workout-steps, then publishes
``activity.created``. It has **no** knowledge of ``.gpx``/``.tcx``/``.fit``, Strava,
or Garmin — the ``activity_ingestion`` adapters produce the contract and call here.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activities_schema
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_workout_steps.crud as activity_workout_steps_crud


def store_parsed_activity(
    parsed: activities_schema.ParsedActivity,
    db: Session,
) -> activities_schema.Activity:
    """Persist a parsed activity and its children, then publish ``activity.created``.

    Args:
        parsed: The canonical parsed activity to store.
        db: Database session.

    Returns:
        The created activity schema (with generated id / ``created_at``).

    Raises:
        HTTPException: 500 when the activity could not be created.
    """
    created_activity = activities_crud.create_activity(parsed.activity, db)

    if created_activity is None or created_activity.id is None:
        core_logger.print_to_log(
            "Error in store_parsed_activity - activity is None, error creating activity",
            "error",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating activity",
        )

    core_logger.print_to_log(
        f"store_parsed_activity: created activity {created_activity.id} for user {created_activity.user_id}",
        "debug",
    )

    if parsed.streams:
        streams = [
            activity_streams_schema.ActivityStreamsCreate(
                activity_id=created_activity.id,
                stream_type=stream.stream_type,
                stream_waypoints=stream.stream_waypoints,
                strava_activity_stream_id=None,
            )
            for stream in parsed.streams
        ]
        activity_streams_crud.create_activity_streams(streams, created_activity, db)

    if parsed.laps is not None:
        activity_laps_crud.create_activity_laps(parsed.laps, created_activity.id, db)

    if parsed.workout_steps is not None:
        activity_workout_steps_crud.create_activity_workout_steps(parsed.workout_steps, created_activity.id, db)

    if parsed.sets is not None:
        activity_sets_crud.create_activity_sets(parsed.sets, created_activity.id, db)

    core_logger.print_to_log(
        f"store_parsed_activity {created_activity.id}: streams={len(parsed.streams)}, "
        f"laps={parsed.laps is not None}, "
        f"workout_steps={parsed.workout_steps is not None}, "
        f"sets={parsed.sets is not None}",
        "debug",
    )

    # Publish the domain fact. Derived work reacts by subscribing to
    # ``activity.created``; this service has no knowledge of what consumes it.
    # Best-effort (the stored activity is the source of truth); the session is
    # passed so durable jobs can stage the event in the outbox.
    activity_event_publishers.publish_activity_created(
        created_activity.id,
        created_activity.user_id,
        duplicate_start_time=created_activity.is_hidden,
        db=db,
    )

    return created_activity
