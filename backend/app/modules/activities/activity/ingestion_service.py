"""Core activity ingestion — persist a canonical :class:`ParsedActivity`.

This is the seam that makes parsing irrelevant to the activities core:
it accepts a format-agnostic :class:`~modules.activities.activity.schema.ParsedActivity`
and persists the activity plus its streams/laps/sets/workout-steps, then publishes
``activity.created``. It has **no** knowledge of ``.gpx``/``.tcx``/``.fit``, Strava,
or Garmin — the ``activity_ingestion`` adapters produce the contract and call here.
"""

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
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


def _derive_dedup_key(
    activity: activities_schema.Activity,
    source: activities_schema.ImportSource | None,
) -> str | None:
    """Derive a stable idempotency key for an activity.

    Precedence:

    1. **Provider id** — Strava then Garmin Connect (both on the core ``Activity``
       schema). Provider ids are stable across server-side re-processing/edits, so
       they are the canonical identity for provider syncs.
    2. **File content hash** — for file-based sources (upload / bulk import) that
       carry no provider id, ``source.content_hash`` (the SHA-256 of the parsed
       file) plus the activity's start time. The start-time salt keeps multiple
       activities parsed from one multi-activity ``.fit`` (which share a file
       hash) distinct.
    3. ``None`` — nothing to key on; ``create_activity`` falls back to start-time
       dedup (marks a duplicate hidden rather than a no-op).

    Stays free of any file-format or provider-module coupling: it reads only the
    core schema + the ``ImportSource`` contract.
    """
    if activity.strava_activity_id is not None:
        return f"strava:{activity.strava_activity_id}"
    if activity.garminconnect_activity_id is not None:
        return f"garmin:{activity.garminconnect_activity_id}"
    if source is not None and source.content_hash and isinstance(activity.start_time, datetime):
        return f"file:{source.content_hash}:{int(activity.start_time.timestamp())}"
    return None


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
    try:
        # Idempotency: a stable dedup_key makes re-import of an
        # already-ingested activity a true no-op. Prefer an explicit key from the
        # source, otherwise derive one from the activity's provider ids. When a
        # key is present and already stored for this owner, return the existing
        # activity without creating a duplicate row, its children, or
        # re-publishing ``activity.created``.
        source = parsed.source
        dedup_key = (
            source.dedup_key if source is not None and source.dedup_key else _derive_dedup_key(parsed.activity, source)
        )

        if dedup_key is not None and parsed.activity.user_id is not None:
            existing = activities_crud.get_activity_by_dedup_key(dedup_key, parsed.activity.user_id, db)
            if existing is not None:
                core_logger.print_to_log(
                    f"store_parsed_activity: dedup_key {dedup_key} already ingested as "
                    f"activity {existing.id} for user {parsed.activity.user_id}; "
                    "skipping re-import (no-op).",
                    "info",
                )
                return existing

        created_activity = activities_crud.create_activity(parsed.activity, db, commit=False, dedup_key=dedup_key)

        if created_activity is None or created_activity.id is None:
            core_logger.print_to_log(
                "Error in store_parsed_activity - activity is None, error creating activity",
                "error",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creating activity",
            )

        source_kind = source.kind if source is not None else "unknown"
        core_logger.print_to_log(
            f"store_parsed_activity: created activity {created_activity.id} "
            f"for user {created_activity.user_id} (source={source_kind})",
            "debug",
        )

        # Persist all children with commit=False so the activity and everything
        # hanging off it land in ONE transaction (committed once below). A failure
        # here rolls the whole unit of work back — there is never a partial
        # activity (a row with no streams/laps/sets/steps).
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
            activity_streams_crud.create_activity_streams(streams, created_activity, db, commit=False)

        if parsed.laps is not None:
            activity_laps_crud.create_activity_laps(parsed.laps, created_activity.id, db, commit=False)

        if parsed.workout_steps is not None:
            activity_workout_steps_crud.create_activity_workout_steps(
                parsed.workout_steps, created_activity.id, db, commit=False
            )

        if parsed.sets is not None:
            activity_sets_crud.create_activity_sets(parsed.sets, created_activity.id, db, commit=False)

        core_logger.print_to_log(
            f"store_parsed_activity {created_activity.id}: streams={len(parsed.streams)}, "
            f"laps={parsed.laps is not None}, "
            f"workout_steps={parsed.workout_steps is not None}, "
            f"sets={parsed.sets is not None}",
            "debug",
        )

        # Publish the domain fact and commit the unit of work atomically. Derived
        # work reacts by subscribing to ``activity.created``; this service has no
        # knowledge of what consumes it. ``publish_activity_created`` owns the
        # commit ordering (via ``commit=db.commit``): when durable jobs are enabled
        # the outbox row joins this transaction and commits with the domain rows;
        # otherwise the domain commits first and the event dispatches on the bus
        # post-commit (best-effort — the stored activity is the source of truth).
        activity_event_publishers.publish_activity_created(
            created_activity.id,
            created_activity.user_id,
            duplicate_start_time=created_activity.is_hidden,
            db=db,
            commit=db.commit,
        )

        return created_activity
    except HTTPException:
        # Roll back the in-flight unit of work so no partial rows survive and the
        # session stays clean for the caller (bulk import reuses one session).
        db.rollback()
        raise
    except SQLAlchemyError as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in store_parsed_activity - {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating activity",
        ) from err
