"""CRUD operations for activity stream data."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import activities.activity.crud as activity_crud
import activities.activity.models as activity_models
import activities.activity.schema as activity_schema
import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.models as activity_streams_models
import activities.activity_streams.schema as activity_streams_schema
import activities.activity_streams.utils as activity_streams_utils
import core.decorators as core_decorators
import core.logger as core_logger
import server_settings.utils as server_settings_utils
import users.users.crud as users_crud
import users.users.models as users_models


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
    activity: activity_schema.Activity | None = activity_crud.get_activity_by_id(activity_id, db)

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
    activity: activity_schema.Activity | None = activity_crud.get_activity_by_id(activity_id, db)

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
async def create_activity_streams(
    activity_streams: list[activity_streams_schema.ActivityStreamsCreate],
    activity: activity_schema.Activity,
    db: Session,
) -> None:
    """
    Bulk create activity streams.

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

    user: users_models.Users | None = users_crud.get_user_by_id(activity.user_id, db)
    if not user:
        core_logger.print_to_log_and_console(
            f"Failed to create activity streams: user {activity.user_id} not found",
            "warning",
        )
        return

    streams: list[activity_streams_models.ActivityStreams] = []
    for stream in activity_streams:
        zone_percentages: dict | None = None
        if stream.stream_type == activity_streams_constants.STREAM_TYPE_HR:
            try:
                zone_percentages = await activity_streams_utils.build_zone_percentages(
                    user,
                    activity,
                    stream.stream_waypoints,
                )
            except Exception as err:
                core_logger.print_to_log(
                    f"Zone % computation failed for stream (activity {stream.activity_id}): {err}",
                    "error",
                    exc=err,
                )
        streams.append(
            activity_streams_models.ActivityStreams(
                activity_id=stream.activity_id,
                stream_type=stream.stream_type,
                stream_waypoints=stream.stream_waypoints,
                strava_activity_stream_id=stream.strava_activity_stream_id,
                zone_percentages=zone_percentages,
            )
        )

    if streams:
        db.add_all(streams)
        db.commit()
