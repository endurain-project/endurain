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
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.activities.activity_streams.utils as activity_streams_utils
import modules.users.users.integration_service as users_integration_service

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
        logger.debug(
            "Refused a streams read; answering with an empty list",
            extra=core_logger.context(activity_id=activity_id, requester_user_id=requester_user_id),
        )
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
        logger.debug(
            "Refused a public streams read; answering with an empty list",
            extra=core_logger.context(activity_id=activity_id),
        )
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


# ---------------------------------------------------------------------------
# Derived-artifact reads
#
# The sibling surface: the thumbnail and geocoding subsystems need an activity's
# recorded track to render a map or resolve a place name. They read it through
# these instead of importing ``activity_streams.crud``, which made each of them a
# second owner of the streams table. No masking is applied and none is wanted —
# the caller is deriving an artifact for the owner, not serving a viewer.


def get_stream_for_derivation(
    activity_id: int,
    stream_type: int,
    db: Session,
) -> activity_streams_schema.ActivityStreamsRead | None:
    """Return one raw stream of an activity for a derived-artifact producer.

    Args:
        activity_id: The parent activity.
        stream_type: The stream type code.
        db: Database session.

    Returns:
        The stream, or ``None`` when the activity has no such stream.
    """
    return activity_streams_crud.get_activity_stream_by_type(activity_id, stream_type, db)


def get_gps_waypoints_for_activities(activity_ids: list[int], db: Session) -> dict[int, list]:
    """Return each activity's GPS waypoints, keyed by activity id.

    The batch read behind the thumbnail and geocoding backfills: one query for
    many activities rather than one per activity. Activities with no GPS stream
    are absent from the result.

    Args:
        activity_ids: The activities to fetch waypoints for.
        db: Database session.

    Returns:
        Mapping of ``activity_id -> waypoints``.
    """
    return activity_streams_crud.get_gps_stream_waypoints_for_activities(activity_ids, db)


# ---------------------------------------------------------------------------
# Heart-rate zone scoring
#
# "What is this athlete's max heart rate?" is a users question, and the answer
# scales every zone. Asking it used to happen inside ``crud``, mid-batch —
# persistence pausing to consult another bounded context. The loop lives here
# now: the service resolves the max HR, computes each breakdown, and hands crud
# a plain ``{stream_id: zones}`` map to store.


def _zones_for(
    stream: activity_streams_contracts.HrStreamForScoring,
    max_heart_rate: int | None,
) -> dict | None:
    """Compute one stream's zone breakdown, or ``None`` when it cannot be scored."""
    if not max_heart_rate:
        return None
    breakdown = activity_streams_utils.compute_hr_zone_breakdown_sync(
        stream.waypoints,
        max_heart_rate,
        stream.total_timer_time,
    )
    return {"hr": breakdown} if breakdown else None


def _max_heart_rate_of(user_id: int, db: Session) -> int | None:
    """Resolve a user's max heart rate, or ``None`` when it cannot be derived."""
    user = users_integration_service.get_user(user_id, db)
    return activity_streams_utils.resolve_max_heart_rate(user) if user is not None else None


def recompute_hr_zones_for_user(user_id: int, db: Session) -> None:
    """Recompute every stored HR-zone breakdown for one user.

    Called after the user's max heart rate or birthdate changes, so activities
    imported earlier reflect the new zones. Errors are logged and swallowed: a
    recompute problem must not fail the profile edit that triggered it.

    Args:
        user_id: The user whose HR streams should be refreshed.
        db: Database session.

    Returns:
        None.
    """
    try:
        max_heart_rate = _max_heart_rate_of(user_id, db)
        last_id = 0
        while True:
            batch = activity_streams_crud.list_user_hr_streams(user_id, db, after_id=last_id)
            if not batch:
                break
            activity_streams_crud.set_zone_percentages(
                {stream.stream_id: _zones_for(stream, max_heart_rate) for stream in batch},
                db,
            )
            last_id = batch[-1].stream_id
        logger.info(
            "Recomputed HR zone percentages for a user",
            extra=core_logger.context(user_id=user_id),
        )
    except Exception as err:
        logger.error(
            "Failed to recompute HR zone percentages for user",
            exc_info=err,
            extra=core_logger.context(console=True, user_id=user_id),
        )


def score_activity_hr_zones(activity_id: int, user_id: int, db: Session) -> None:
    """Compute and store the HR-zone breakdown for one activity.

    Driven by the ``activity.created`` subscriber so scoring stays off the
    synchronous ingestion path. No-ops when the owner has no resolvable max heart
    rate or the activity recorded no heart rate. Raises on database error so the
    durable handler can retry.

    Args:
        activity_id: The activity whose HR stream should be scored.
        user_id: The owning user, whose max heart rate scales the zones.
        db: Database session.

    Returns:
        None.
    """
    max_heart_rate = _max_heart_rate_of(user_id, db)
    if not max_heart_rate:
        return
    stream = activity_streams_crud.get_activity_hr_stream(activity_id, db)
    if stream is None:
        return
    activity_streams_crud.set_zone_percentages({stream.stream_id: _zones_for(stream, max_heart_rate)}, db)


def backfill_missing_hr_zones(db: Session, batch_size: int = 500) -> int:
    """Score HR streams that carry no zone breakdown yet (reconciliation net).

    The scheduled safety net for the ``activity.created`` HR-zone subscriber.
    Each owner's max heart rate is resolved once per run; streams whose owner has
    none are left untouched so a later profile edit can still score them.

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
        batch = activity_streams_crud.list_hr_streams_missing_zones(db, after_id=last_id, batch_size=batch_size)
        if not batch:
            break
        zones_by_stream_id: dict[int, dict | None] = {}
        for stream in batch:
            if stream.owner_id not in max_hr_cache:
                max_hr_cache[stream.owner_id] = _max_heart_rate_of(stream.owner_id, db)
            zones = _zones_for(stream, max_hr_cache[stream.owner_id])
            if zones is not None:
                zones_by_stream_id[stream.stream_id] = zones
        activity_streams_crud.set_zone_percentages(zones_by_stream_id, db)
        updated += len(zones_by_stream_id)
        last_id = batch[-1].stream_id
    return updated
