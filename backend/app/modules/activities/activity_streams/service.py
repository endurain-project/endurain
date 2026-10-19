"""Application-layer orchestration for activity streams.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses, and owns the access decision so ``crud`` is left with nothing but
persistence.

Streams mask differently from the other child resources: there is no single
``hide_streams`` flag, because each stream *type* is gated by its own parent flag
(``hide_hr``, ``hide_power``, ``hide_cadence``, ...). So instead of the boolean
gate the siblings use, this module resolves the parent activity through
:mod:`modules.activities.activity.child_access_service` and decides per stream
itself: an activity can hide its heart rate while still publishing its route.

They are also the one child resource whose page is not cut in SQL, deliberately.
Laps, sets and workout steps have no domain ceiling on their row count, so a read
of "all of them" is unbounded work that has to be bounded by a ``LIMIT``. A stream
row count is bounded by the closed ``stream_type`` enum (one row per type,
validated on the way in), and the per-type mask is applied *after* the read, so a
SQL window would page rows the caller may not see. They are therefore read whole,
masked, and then cut in Python — the same
:class:`~core.pagination.Page` envelope the siblings answer with, so a client has
one list contract rather than one per child resource, over a total that already
reflects the mask. What is large here is ``stream_waypoints`` — the samples inside
one row — which page numbers cannot bound; reducing that is a downsampling
question, not a pagination one, and is deliberately left alone rather than
answered with a control that looks like a fix without being one.
"""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import core.pagination as core_pagination
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.hr_zones as activity_streams_hr_zones
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

# Map stream type to activity hide attribute
_STREAM_HIDE_MAP: dict[int, str] = {
    activity_streams_constants.STREAM_TYPE_HR: "hide_hr",
    activity_streams_constants.STREAM_TYPE_POWER: "hide_power",
    activity_streams_constants.STREAM_TYPE_CADENCE: "hide_cadence",
    activity_streams_constants.STREAM_TYPE_ELEVATION: "hide_elevation",
    activity_streams_constants.STREAM_TYPE_SPEED: "hide_speed",
    activity_streams_constants.STREAM_TYPE_PACE: "hide_pace",
    activity_streams_constants.STREAM_TYPE_MAP: "hide_map",
}


def _is_stream_hidden(activity: activity_schema.ActivityRead, stream_type: int) -> bool:
    """Return whether the activity hides a stream type from other viewers.

    Args:
        activity: The parent activity.
        stream_type: The stream type code.

    Returns:
        True when the parent's hide flag for this stream type is set.
    """
    attr = _STREAM_HIDE_MAP.get(stream_type)
    return bool(attr and getattr(activity, attr, False))


def _filter_visible_streams(
    streams: list[activity_streams_schema.ActivityStreamsRead],
    activity: activity_schema.ActivityRead,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Drop the streams the activity hides from other viewers.

    Args:
        streams: The activity's streams, as read schemas.
        activity: The parent activity.

    Returns:
        The streams that are not hidden.
    """
    return [stream for stream in streams if not _is_stream_hidden(activity, stream.stream_type)]


def _page_of(
    streams: list[activity_streams_schema.ActivityStreamsRead],
    page_number: int,
    num_records: int,
) -> activity_streams_schema.ActivityStreamsPage:
    """Cut an already-masked stream list into the shared page envelope.

    Args:
        streams: The streams the caller may see, in read order.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope, whose ``total`` counts only the visible streams.
    """
    start = (page_number - 1) * num_records
    return activity_streams_schema.ActivityStreamsPage.build(
        streams[start : start + num_records],
        len(streams),
        page_number,
        num_records,
    )


def _max_heart_rate_of(user_id: int, db: Session) -> int | None:
    """Resolve a user's max heart rate, or ``None`` when it cannot be derived.

    Args:
        user_id: ID of the stream's owner.
        db: Database session.

    Returns:
        The max heart rate, or None when it cannot be derived.
    """
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    return activity_streams_hr_zones.resolve_max_heart_rate(user.max_heart_rate, user.birthdate, user.timezone)


def _with_zones(
    streams: list[activity_streams_schema.ActivityStreamsRead],
    activity: activity_schema.ActivityRead,
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Attach the heart-rate zone breakdown to the HR streams being served.

    Zones are a function of the samples, the activity's timer time and the
    owner's *current* max heart rate (which itself follows their age), so they are
    computed here, per read, rather than stored: a stored value is stale the
    moment the owner edits their profile or has a birthday, and keeping it
    fresh costs a pass over every stream the user owns. The pass over one
    stream's samples is cheap next to serializing them.

    Only streams the caller may see reach this, and the owner is looked up once,
    only when one of them is an HR stream.

    Args:
        streams: The streams about to be served, already masked.
        activity: The parent activity, for its owner and timer time.
        db: Database session.

    Returns:
        The streams, the HR one carrying ``zone_percentages`` when the owner's
        max heart rate is known and the stream has samples.
    """
    if not any(stream.stream_type == activity_streams_constants.STREAM_TYPE_HR for stream in streams):
        return streams
    if activity.user_id is None:
        return streams
    max_heart_rate = _max_heart_rate_of(activity.user_id, db)
    if not max_heart_rate:
        return streams

    with_zones: list[activity_streams_schema.ActivityStreamsRead] = []
    for stream in streams:
        if stream.stream_type == activity_streams_constants.STREAM_TYPE_HR:
            breakdown = activity_streams_hr_zones.compute_hr_zone_breakdown_sync(
                stream.stream_waypoints,
                max_heart_rate,
                activity.total_timer_time,
            )
            if breakdown:
                stream = stream.model_copy(update={"zone_percentages": {"hr": breakdown}})
        with_zones.append(stream)
    return with_zones


def list_activity_streams(
    activity_id: int,
    requester_user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_streams_schema.ActivityStreamsPage:
    """Return an activity's streams for an authenticated caller, masked per type.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope. An empty page when the activity is not visible to the
        caller or has none.
    """
    activity = activity_integration.resolve_readable_parent(activity_id, requester_user_id, db)
    if activity is None:
        logger.debug(
            "Refused a streams read; answering with an empty page",
            extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id),
        )
        return _page_of([], page_number, num_records)

    streams = activity_streams_crud.get_activity_streams(activity_id, db)
    if requester_user_id != activity.user_id:
        streams = _filter_visible_streams(streams, activity)

    return _page_of(_with_zones(streams, activity, db), page_number, num_records)


def get_activity_stream(
    activity_id: int,
    stream_type: int,
    requester_user_id: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead:
    """Return one stream type of an activity for an authenticated caller.

    Args:
        activity_id: The parent activity.
        stream_type: The stream type code.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The stream.

    Raises:
        NotFoundError: When the activity is not visible, has no such
        stream, or the stream is hidden from this caller — indistinguishable on purpose, so the
            endpoint cannot be used to probe which activities exist.
    """
    activity = activity_integration.resolve_readable_parent(activity_id, requester_user_id, db)
    if activity is None:
        raise core_exceptions.NotFoundError("Activity stream not found")

    stream = activity_streams_crud.get_activity_stream_by_type(activity_id, stream_type, db)
    if stream is None:
        raise core_exceptions.NotFoundError("Activity stream not found")

    if requester_user_id != activity.user_id and _is_stream_hidden(activity, stream.stream_type):
        raise core_exceptions.NotFoundError("Activity stream not found")

    return _with_zones([stream], activity, db)[0]


def list_public_activity_streams(
    activity_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_CHILD_NUM_RECORDS,
) -> activity_streams_schema.ActivityStreamsPage:
    """Return a publicly shared activity's streams, masked per type.

    Args:
        activity_id: The parent activity.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The page envelope, empty when the activity is not publicly shareable.
    """
    activity = activity_integration.resolve_public_parent(activity_id, db)
    if activity is None:
        logger.debug(
            "Refused a public streams read; answering with an empty page",
            extra=core_logger.context(activity_id=activity_id),
        )
        return _page_of([], page_number, num_records)

    streams = activity_streams_crud.get_activity_streams(activity_id, db)
    return _page_of(
        _with_zones(_filter_visible_streams(streams, activity), activity, db),
        page_number,
        num_records,
    )


def get_public_activity_stream(
    activity_id: int,
    stream_type: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead:
    """Return one stream type of a publicly shared activity.

    Args:
        activity_id: The parent activity.
        stream_type: The stream type code.
        db: Database session.

    Returns:
        The stream.

    Raises:
        NotFoundError: When the activity is not publicly shareable, has
        no such stream, or the stream is hidden — indistinguishable on purpose, so the
            endpoint cannot be used to probe which activities exist.
    """
    activity = activity_integration.resolve_public_parent(activity_id, db)
    if activity is None:
        raise core_exceptions.NotFoundError("Activity stream not found")

    stream = activity_streams_crud.get_activity_stream_by_type(activity_id, stream_type, db)
    if stream is None:
        raise core_exceptions.NotFoundError("Activity stream not found")

    if _is_stream_hidden(activity, stream.stream_type):
        raise core_exceptions.NotFoundError("Activity stream not found")

    return _with_zones([stream], activity, db)[0]
