"""Application-layer orchestration for activity streams.

Sits between the thin route and :mod:`crud`, matching the layering the activities
core uses, and owns the access decision so ``crud`` is left with nothing but
persistence.

Streams mask differently from the other child resources: there is no single
``hide_streams`` flag, because each stream *type* is gated by its own parent flag
(``hide_hr``, ``hide_power``, ``hide_cadence``, ...). So instead of the boolean
gate the siblings use, this module resolves the parent activity through
:mod:`modules.activities.activity.child_access` and hands it to
:mod:`~modules.activities.activity_streams.utils`, which decides per stream.

They are also the one child resource that is **not** paginated, deliberately.
Laps, sets and workout steps have no domain ceiling on their row count, so a
read of "all of them" is unbounded work. A stream row count is bounded by the
closed ``stream_type`` enum (one row per type, validated on the way in), so
paging them would cap a number that is already capped at single digits. What is
large here is ``stream_waypoints`` — the samples inside one row — which page
numbers cannot bound; reducing that is a downsampling question, not a pagination
one, and is deliberately left alone rather than answered with a control that
looks like a fix without being one.
"""

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.child_access as activity_child_access
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.utils as activity_streams_utils

logger = core_logger.get_logger(__name__)


def list_activity_streams(
    activity_id: int,
    requester_user_id: int,
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Return an activity's streams for an authenticated caller, masked per type.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The visible streams, empty when the activity is not visible to the caller
        or has none.
    """
    activity = activity_child_access.resolve_readable_parent(activity_id, requester_user_id, db)
    if activity is None:
        return []

    streams = activity_streams_crud.get_activity_streams(activity_id, db)
    if requester_user_id != activity.user_id:
        streams = activity_streams_utils.filter_visible_streams(streams, activity)

    return streams


def get_activity_stream(
    activity_id: int,
    stream_type: int,
    requester_user_id: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead | None:
    """Return one stream type of an activity for an authenticated caller.

    Args:
        activity_id: The parent activity.
        stream_type: The stream type code.
        requester_user_id: The authenticated caller.
        db: Database session.

    Returns:
        The stream, or ``None`` when the activity is not visible, has no such
        stream, or the stream is hidden from this caller.
    """
    activity = activity_child_access.resolve_readable_parent(activity_id, requester_user_id, db)
    if activity is None:
        return None

    stream = activity_streams_crud.get_activity_stream_by_type(activity_id, stream_type, db)
    if stream is None:
        return None

    if requester_user_id != activity.user_id and activity_streams_utils.is_stream_hidden(activity, stream.stream_type):
        return None

    return stream


def list_public_activity_streams(
    activity_id: int,
    db: Session,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """Return a publicly shared activity's streams, masked per type.

    Args:
        activity_id: The parent activity.
        db: Database session.

    Returns:
        The visible streams, empty when the activity is not publicly shareable.
    """
    activity = activity_child_access.resolve_public_parent(activity_id, db)
    if activity is None:
        return []

    streams = activity_streams_crud.get_activity_streams(activity_id, db)
    return activity_streams_utils.filter_visible_streams(streams, activity)


def get_public_activity_stream(
    activity_id: int,
    stream_type: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead | None:
    """Return one stream type of a publicly shared activity.

    Args:
        activity_id: The parent activity.
        stream_type: The stream type code.
        db: Database session.

    Returns:
        The stream, or ``None`` when the activity is not publicly shareable, has
        no such stream, or the stream is hidden.
    """
    activity = activity_child_access.resolve_public_parent(activity_id, db)
    if activity is None:
        return None

    stream = activity_streams_crud.get_activity_stream_by_type(activity_id, stream_type, db)
    if stream is None:
        return None

    if activity_streams_utils.is_stream_hidden(activity, stream.stream_type):
        return None

    return stream
