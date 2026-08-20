"""CRUD operations for activity stream data."""

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.models as activity_streams_models
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.utils as activity_streams_utils

logger = core_logger.get_logger(__name__)


@core_decorators.handle_db_errors
def get_activity_streams(
    activity_id: int,
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """
    Get every stream belonging to an activity.

    Performs no access check and no per-type masking: both are decided by
    :mod:`modules.activities.activity_streams.service`.

    Args:
        activity_id: The activity identifier.
        db: Database session.

    Returns:
        The activity's streams, empty when it has none.

    Raises:
        ProcessingError: On database errors.
    """
    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity_id,
    )
    activity_streams: list[activity_streams_models.ActivityStreams] = list(db.scalars(stmt).all())

    return activity_streams_utils.transform_activity_streams(activity_streams)


@core_decorators.handle_db_errors
def get_activities_streams(
    activity_ids: list[int],
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """
    Get streams for multiple activities.

    Performs no access check: which activities the caller may read is decided
    before this is reached, by the activities integration service that owns them.

    Args:
        activity_ids: The activities to read, already scoped to the caller.
        db: Database session.

    Returns:
        List of activity streams.

    Raises:
        ProcessingError: On database errors.
    """
    if not activity_ids:
        return []
    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id.in_(activity_ids)
    )
    all_streams: list[activity_streams_models.ActivityStreams] = list(db.scalars(stmt).all())

    if not all_streams:
        return []

    return activity_streams_utils.transform_activity_streams(all_streams)


@core_decorators.handle_db_errors
def get_activity_stream_by_type(
    activity_id: int,
    stream_type: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead | None:
    """
    Get a specific stream type for an activity.

    Performs no access check and no masking: both are decided by
    :mod:`modules.activities.activity_streams.service`.

    Args:
        activity_id: The activity identifier.
        stream_type: The stream type constant.
        db: Database session.

    Returns:
        The activity stream, or ``None`` when the activity has no such stream.

    Raises:
        ProcessingError: On database errors.
    """
    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity_id,
        activity_streams_models.ActivityStreams.stream_type == stream_type,
    )
    activity_stream: activity_streams_models.ActivityStreams | None = db.scalars(stmt).first()

    if not activity_stream:
        return None

    return activity_streams_utils.transform_activity_streams(activity_stream)


def get_gps_stream_waypoints_for_activities(
    activity_ids: list[int],
    db: Session,
) -> dict[int, list]:
    """Return each activity's GPS (map) stream waypoints, keyed by activity id.

    Batch helper for the reverse-geocoding backfill: it fetches only the
    ``STREAM_TYPE_MAP`` waypoints for the given activities in one query and keeps
    the ORM confined to this module (returning plain lists, not ORM rows).
    Activities without a GPS stream are simply absent from the result.

    Args:
        activity_ids: Activity ids to fetch GPS waypoints for.
        db: Database session.

    Returns:
        Mapping of ``activity_id -> waypoints`` (empty when ``activity_ids`` is
        empty).
    """
    if not activity_ids:
        return {}
    stmt = select(
        activity_streams_models.ActivityStreams.activity_id,
        activity_streams_models.ActivityStreams.stream_waypoints,
    ).where(
        activity_streams_models.ActivityStreams.activity_id.in_(activity_ids),
        activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_MAP,
    )
    return {activity_id: (waypoints or []) for activity_id, waypoints in db.execute(stmt).all()}


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
        logger.error(
            "Failed to backfill zone percentages for HR streams",
            exc_info=err,
            extra=core_logger.context(console=True),
        )


def _to_hr_record(stream: activity_streams_models.ActivityStreams) -> activity_streams_contracts.HrStreamRecord:
    """Project one stream ORM row into a package-owned record."""
    return activity_streams_contracts.HrStreamRecord(
        stream_id=stream.id,
        activity_id=stream.activity_id,
        waypoints=stream.stream_waypoints or [],
    )


@core_decorators.handle_db_errors
def list_hr_streams_for_activities(
    activity_ids: list[int],
    db: Session,
) -> list[activity_streams_contracts.HrStreamRecord]:
    """Return HR streams for activity ids already scoped by the caller."""
    if not activity_ids:
        return []
    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id.in_(activity_ids),
        activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_HR,
    )
    return [_to_hr_record(stream) for stream in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def list_hr_streams_missing_zones(
    db: Session,
    *,
    after_id: int = 0,
    batch_size: int = 500,
) -> list[activity_streams_contracts.HrStreamRecord]:
    """
    Return a batch of HR streams that carry no zone breakdown yet.

    Args:
        db: Database session.
        after_id: Return only streams with an id greater than this.
        batch_size: Maximum number of streams to return.

    Returns:
        The batch, id-ordered; empty when there are no more.

    Raises:
        ProcessingError: On database error.
    """
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
    return [_to_hr_record(stream) for stream in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_activity_hr_stream(
    activity_id: int,
    db: Session,
) -> activity_streams_contracts.HrStreamRecord | None:
    """
    Return one activity's HR stream, ready for zone scoring.

    Args:
        activity_id: The activity whose HR stream to read.
        db: Database session.

    Returns:
        The stream, or None when the activity recorded no heart rate.

    Raises:
        ProcessingError: On database error.
    """
    stmt = select(activity_streams_models.ActivityStreams).where(
        activity_streams_models.ActivityStreams.activity_id == activity_id,
        activity_streams_models.ActivityStreams.stream_type == activity_streams_constants.STREAM_TYPE_HR,
    )
    stream = db.scalars(stmt).first()
    return _to_hr_record(stream) if stream is not None else None


@core_decorators.handle_db_errors
def set_zone_percentages(zones_by_stream_id: dict[int, dict | None], db: Session) -> None:
    """
    Store the computed HR zone breakdown against each stream.

    Args:
        zones_by_stream_id: Stream id -> breakdown, or None to clear it.
        db: Database session.

    Returns:
        None.

    Raises:
        ProcessingError: On database error.
    """
    if not zones_by_stream_id:
        return
    for stream_id, zones in zones_by_stream_id.items():
        db.execute(
            sa_update(activity_streams_models.ActivityStreams)
            .where(activity_streams_models.ActivityStreams.id == stream_id)
            .values(zone_percentages=zones)
        )
    db.commit()


@core_decorators.handle_db_errors
def create_activity_streams(
    activity_streams: list[activity_streams_schema.ActivityStreamsCreate],
    activity: activity_schema.Activity,
    db: Session,
    *,
    commit: bool = True,
) -> None:
    """
    Bulk create activity streams (waypoints only).

    HR ``zone_percentages`` are no longer computed here: that work is decoupled to
    the ``activity.created`` subscriber so ingestion stays synchronous
    and fast. Streams are persisted with ``zone_percentages=None``; the subscriber
    (and the scheduled backfill reconciliation net) fill them in.

    Args:
        activity_streams: List of stream schemas.
        activity: Activity schema to associate streams with.
        db: Database session.
    """
    if activity.user_id is None:
        logger.warning(
            "Failed to create activity streams: activity has no user_id",
            extra=core_logger.context(console=True, activity_id=activity.id),
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
        # commit=False leaves the streams in the caller's open transaction so the
        # whole activity ingestion is one atomic unit of work.
        if commit:
            db.commit()
        else:
            db.flush()
