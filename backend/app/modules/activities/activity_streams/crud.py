"""CRUD operations for activity stream data."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.models as activity_streams_models
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.utils as activity_streams_utils
import modules.server_settings.utils as server_settings_utils
import modules.users.users.crud as users_crud


@core_decorators.handle_db_errors
def get_activity_streams(
    activity_id: int,
    token_user_id: int,
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """
    Get all streams for an activity.

    Args:
        activity_id: The activity identifier.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        List of activity streams or None.

    Raises:
        HTTPException: On database errors.
    """
    activity: activity_schema.Activity | None = activity_crud.get_viewable_activity_by_id_for_user(
        activity_id, token_user_id, db
    )

    if not activity:
        return []

    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity_id,
    )
    activity_streams: list[activity_streams_models.ActivityStreams] = list(db.scalars(stmt).all())

    if not activity_streams:
        return []

    if token_user_id != activity.user_id:
        activity_streams = activity_streams_utils.filter_visible_streams(activity_streams, activity)

    return activity_streams_utils.transform_activity_streams(activity_streams)


@core_decorators.handle_db_errors
def get_activities_streams(
    activity_ids: list[int],
    _user_id: int,
    db: Session,
    _activities: list[activity_models.Activity],
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """
    Get streams for multiple activities.

    Args:
        activity_ids: List of activity IDs.
        _user_id: Authenticated user ID.
        db: Database session.
        _activities: Pre-fetched activity list.

    Returns:
        List of activity streams.

    Raises:
        HTTPException: On database errors.
    """
    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id.in_(activity_ids)
    )
    all_streams: list[activity_streams_models.ActivityStreams] = list(db.scalars(stmt).all())

    if not all_streams:
        return []

    return activity_streams_utils.transform_activity_streams(all_streams)


@core_decorators.handle_db_errors
def get_public_activity_streams(
    activity_id: int,
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """
    Get public streams for an activity.

    Args:
        activity_id: The activity identifier.
        db: Database session.

    Returns:
        List of activity streams.

    Raises:
        HTTPException: On database errors.
    """
    server_settings = server_settings_utils.get_server_settings_or_404(db)

    if not server_settings.public_shareable_links:
        return []

    activity = activity_crud.get_activity_by_id_if_is_public(activity_id, db)

    if not activity:
        return []

    stmt = (
        select(activity_streams_models.ActivityStreams)
        .join(
            activity_models.Activity,
            activity_models.Activity.id == (activity_streams_models.ActivityStreams.activity_id),
        )
        .where(
            activity_streams_models.ActivityStreams.activity_id == activity_id,
            activity_models.Activity.visibility == 0,
            activity_models.Activity.id == activity_id,
        )
    )
    activity_streams: list[activity_streams_models.ActivityStreams] = list(db.scalars(stmt).all())

    if not activity_streams:
        return []

    activity_streams = activity_streams_utils.filter_visible_streams(activity_streams, activity)

    return activity_streams_utils.transform_activity_streams(activity_streams)


@core_decorators.handle_db_errors
def get_activity_stream_by_type(
    activity_id: int,
    stream_type: int,
    token_user_id: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead | None:
    """
    Get a specific stream type for an activity.

    Args:
        activity_id: The activity identifier.
        stream_type: The stream type constant.
        token_user_id: Authenticated user ID.
        db: Database session.

    Returns:
        The activity stream or None.

    Raises:
        HTTPException: On database errors.
    """
    activity: activity_schema.Activity | None = activity_crud.get_viewable_activity_by_id_for_user(
        activity_id, token_user_id, db
    )

    if not activity:
        return None

    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity_id,
        activity_streams_models.ActivityStreams.stream_type == stream_type,
    )
    activity_stream: activity_streams_models.ActivityStreams | None = db.scalars(stmt).first()

    if not activity_stream:
        return None

    if token_user_id != activity.user_id and activity_streams_utils.is_stream_hidden(
        activity,
        activity_stream.stream_type,
    ):
        return None

    return activity_streams_utils.transform_activity_streams(activity_stream)


@core_decorators.handle_db_errors
def get_public_activity_stream_by_type(
    activity_id: int,
    stream_type: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead | None:
    """
    Get a public stream by type for an activity.

    Args:
        activity_id: The activity identifier.
        stream_type: The stream type constant.
        db: Database session.

    Returns:
        The activity stream or None.

    Raises:
        HTTPException: On database errors.
    """
    server_settings = server_settings_utils.get_server_settings_or_404(db)

    if not server_settings.public_shareable_links:
        return None

    activity: activity_schema.Activity | None = activity_crud.get_activity_by_id_if_is_public(activity_id, db)

    if not activity:
        return None

    stmt = (
        select(activity_streams_models.ActivityStreams)
        .join(
            activity_models.Activity,
            activity_models.Activity.id == (activity_streams_models.ActivityStreams.activity_id),
        )
        .where(
            activity_streams_models.ActivityStreams.activity_id == activity_id,
            activity_streams_models.ActivityStreams.stream_type == stream_type,
            activity_models.Activity.visibility == 0,
            activity_models.Activity.id == activity_id,
        )
    )
    activity_stream = db.scalars(stmt).first()

    if not activity_stream:
        return None

    if activity_streams_utils.is_stream_hidden(
        activity,
        activity_stream.stream_type,
    ):
        return None

    return activity_streams_utils.transform_activity_streams(activity_stream)


@core_decorators.handle_db_errors
def get_hr_streams_without_zone_percentages(
    db: Session,
    after_id: int = 0,
    batch_size: int = 500,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Return HR streams lacking pre-computed zone_percentages in batches."""
    stmt = (
        select(activity_streams_models.ActivityStreams)
        .where(
            activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_HR,
            activity_streams_models.ActivityStreams.zone_percentages.is_(None),
            activity_streams_models.ActivityStreams.id > after_id,
        )
        .order_by(activity_streams_models.ActivityStreams.id)
        .limit(batch_size)
    )
    return activity_streams_utils.transform_activity_streams(list(db.scalars(stmt).all()))


def backfill_zone_percentages_for_missing_hr_streams(
    computed_streams: list[dict[str, int | dict]],
    db: Session,
) -> None:
    """Backfill zone_percentages for existing HR streams with pre-computed values."""
    for stream in computed_streams:
        db.query(activity_streams_models.ActivityStreams).filter(
            activity_streams_models.ActivityStreams.id == stream["stream_id"],
        ).update(
            {"zone_percentages": stream["zone_percentages"]},
            synchronize_session=False,
        )
    try:
        db.commit()
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Failed to backfill zone_percentages for HR streams: {err}",
            "error",
            exc=err,
        )


def _get_user_hr_streams_batch(
    user_id: int,
    db: Session,
    after_id: int = 0,
    batch_size: int = 500,
) -> list[tuple[activity_streams_models.ActivityStreams, float | None]]:
    """
    Fetch a user's HR streams paired with their activity timer time.

    Args:
        user_id: The user whose HR streams should be fetched.
        db: Database session.
        after_id: Return only streams with an id greater than this.
        batch_size: Maximum number of streams to return.

    Returns:
        List of (HR stream, activity total_timer_time) tuples ordered
        by stream id.
    """
    stmt = (
        select(
            activity_streams_models.ActivityStreams,
            activity_models.Activity.total_timer_time,
        )
        .join(
            activity_models.Activity,
            activity_models.Activity.id == activity_streams_models.ActivityStreams.activity_id,
        )
        .where(
            activity_models.Activity.user_id == user_id,
            activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_HR,
            activity_streams_models.ActivityStreams.id > after_id,
        )
        .order_by(activity_streams_models.ActivityStreams.id)
        .limit(batch_size)
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def recompute_hr_zone_percentages_for_user(user_id: int, db: Session) -> None:
    """
    Recompute stored HR zone_percentages for a user's HR streams.

    Called after the user's max heart rate or birthdate changes so
    activities imported earlier reflect the new zones. Errors are
    logged and swallowed so a recompute problem never fails the
    originating user edit.

    Args:
        user_id: The user whose HR streams should be refreshed.
        db: Database session.

    Returns:
        None.
    """
    try:
        user = users_crud.get_user_by_id(user_id, db)
        if user is None:
            return

        max_heart_rate = activity_streams_utils.resolve_max_heart_rate(user)

        last_id = 0
        while True:
            batch = _get_user_hr_streams_batch(user_id, db, after_id=last_id)
            if not batch:
                break

            for stream, total_timer_time in batch:
                hr_block: dict | None = None
                if max_heart_rate:
                    hr_block = activity_streams_utils.compute_hr_zone_breakdown_sync(
                        stream.stream_waypoints,
                        max_heart_rate,
                        total_timer_time,
                    )
                stream.zone_percentages = {"hr": hr_block} if hr_block else None

            last_id = batch[-1][0].id
            db.commit()
    except Exception as err:
        db.rollback()
        core_logger.print_to_log_and_console(
            f"Failed to recompute HR zone_percentages for user {user_id}: {err}",
            "error",
            exc=err,
        )


@core_decorators.handle_db_errors
def create_activity_streams(
    activity_streams: list[activity_streams_schema.ActivityStreamsCreate],
    activity: activity_schema.Activity,
    db: Session,
) -> None:
    """
    Bulk create activity streams (waypoints only).

    HR ``zone_percentages`` are no longer computed here: that work is decoupled to
    the ``activity.created`` subscriber (plan §6) so ingestion stays synchronous
    and fast. Streams are persisted with ``zone_percentages=None``; the subscriber
    (and the scheduled backfill reconciliation net) fill them in.

    Args:
        activity_streams: List of stream schemas.
        activity: Activity schema to associate streams with.
        db: Database session.
    """
    if activity.user_id is None:
        core_logger.print_to_log_and_console(
            f"Failed to create activity streams: activity {activity.id} has no user_id",
            "warning",
        )
        return

    streams = [
        activity_streams_models.ActivityStreams(
            activity_id=stream.activity_id,
            stream_type=stream.stream_type,
            stream_waypoints=stream.stream_waypoints,
            strava_activity_stream_id=stream.strava_activity_stream_id,
            zone_percentages=None,
        )
        for stream in activity_streams
    ]

    if streams:
        db.add_all(streams)
        db.commit()


def compute_and_store_hr_zone_percentages_for_activity(activity_id: int, user_id: int, db: Session) -> None:
    """Compute and store HR ``zone_percentages`` for one activity's HR stream.

    The per-activity counterpart of :func:`recompute_hr_zone_percentages_for_user`,
    driven by the ``activity.created`` subscriber so HR-zone scoring stays off the
    synchronous ingestion path. No-ops when the owner has no resolvable max heart
    rate or the activity has no HR stream. Raises on database error so the durable
    handler can retry.

    Args:
        activity_id: The activity whose HR stream should be scored.
        user_id: The owning user (for the max-heart-rate lookup).
        db: Database session.

    Returns:
        None.
    """
    user = users_crud.get_user_by_id(user_id, db)
    if user is None:
        return
    max_heart_rate = activity_streams_utils.resolve_max_heart_rate(user)
    if not max_heart_rate:
        return

    row = db.execute(
        select(
            activity_streams_models.ActivityStreams,
            activity_models.Activity.total_timer_time,
        )
        .join(
            activity_models.Activity,
            activity_models.Activity.id == activity_streams_models.ActivityStreams.activity_id,
        )
        .where(
            activity_streams_models.ActivityStreams.activity_id == activity_id,
            activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_HR,
        )
    ).first()
    if row is None:
        return

    stream, total_timer_time = row[0], row[1]
    hr_block = activity_streams_utils.compute_hr_zone_breakdown_sync(
        stream.stream_waypoints,
        max_heart_rate,
        total_timer_time,
    )
    stream.zone_percentages = {"hr": hr_block} if hr_block else None
    db.commit()


def backfill_missing_hr_zone_percentages(db: Session, batch_size: int = 500) -> int:
    """Score HR streams that are missing ``zone_percentages`` (reconciliation net).

    The scheduled safety net for the ``activity.created`` HR-zone subscriber: scans
    HR streams with ``NULL`` ``zone_percentages`` in id-ordered batches, resolves
    each owner's max heart rate (cached per run), and stores the computed zones.
    Streams whose owner has no resolvable max HR are left untouched.

    Args:
        db: Database session.
        batch_size: Number of streams to score per batch.

    Returns:
        The number of streams updated.
    """
    updated = 0
    max_hr_cache: dict[int, int | None] = {}
    last_id = 0
    while True:
        rows = db.execute(
            select(
                activity_streams_models.ActivityStreams,
                activity_models.Activity.total_timer_time,
                activity_models.Activity.user_id,
            )
            .join(
                activity_models.Activity,
                activity_models.Activity.id == activity_streams_models.ActivityStreams.activity_id,
            )
            .where(
                activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_HR,
                activity_streams_models.ActivityStreams.zone_percentages.is_(None),
                activity_streams_models.ActivityStreams.id > last_id,
            )
            .order_by(activity_streams_models.ActivityStreams.id)
            .limit(batch_size)
        ).all()
        if not rows:
            break
        for stream, total_timer_time, owner_id in rows:
            if owner_id not in max_hr_cache:
                owner = users_crud.get_user_by_id(owner_id, db)
                max_hr_cache[owner_id] = activity_streams_utils.resolve_max_heart_rate(owner) if owner else None
            max_hr = max_hr_cache[owner_id]
            if not max_hr:
                continue
            hr_block = activity_streams_utils.compute_hr_zone_breakdown_sync(
                stream.stream_waypoints, max_hr, total_timer_time
            )
            if hr_block:
                stream.zone_percentages = {"hr": hr_block}
                updated += 1
        last_id = rows[-1][0].id
        db.commit()
    return updated
