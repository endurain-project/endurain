"""Application-layer orchestration for activity streams.

Sits between the thin route and :mod:`crud`, matching the layering the activities core uses, and owns the access
decision so ``crud`` is left with nothing but persistence.

An activity's streams are one resource: its samples on one timeline, a list per channel. Each channel is gated by its
own parent flag (``hide_hr``, ``hide_power``, ``hide_cadence``, ...), so an activity can hide its heart rate while
still publishing its route; a hidden channel is ``null`` for a non-owner. ``hide_start_time`` strips nothing: the
offsets count from the start and show only the duration, which the activity shows anyway.

The samples are read whole and masked, then optionally averaged into ``max_points`` buckets, so a client can ask for a
chart-sized series of a long activity. The heart-rate zones are always computed from every sample.
"""

import uuid

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.crud as activity_streams_crud
import modules.activities.activity_streams.hr_zones as activity_streams_hr_zones
import modules.activities.activity_streams.samples as activity_streams_samples
import modules.activities.activity_streams.schema as activity_streams_schema
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

#: The parent ``hide_*`` flag that withholds each served channel from a non-owner, or ``None`` for a channel no flag
#: covers. A channel missing here is withheld, so a new channel stays owner-only until it is given a rule.
_CHANNEL_HIDE_FLAG: dict[str, str | None] = {
    "latitude": "hide_map",
    "longitude": "hide_map",
    "elevation": "hide_elevation",
    "heart_rate": "hide_hr",
    "power": "hide_power",
    "cadence": "hide_cadence",
    "speed": "hide_speed",
    "pace": "hide_pace",
    # Ambient temperature is none of the data a flag covers.
    "temperature": None,
}

#: Every channel the response carries: the stored ones, and pace derived from speed.
_SERVED_CHANNELS = (*activity_streams_constants.SAMPLE_CHANNELS, "pace")


def _is_channel_hidden(activity: activity_schema.ActivityRead, channel: str) -> bool:
    """Return whether the activity hides a channel from other viewers.

    Args:
        activity: The parent activity.
        channel: The served channel name.

    Returns:
        True when the parent's hide flag for the channel is set, or when the channel has no rule.
    """
    if channel not in _CHANNEL_HIDE_FLAG:
        return True
    flag = _CHANNEL_HIDE_FLAG[channel]
    return flag is not None and bool(getattr(activity, flag))


def _max_heart_rate_of(user_id: uuid.UUID, db: Session) -> int | None:
    """Resolve a user's max heart rate, or ``None`` when it cannot be derived.

    Args:
        user_id: ID of the activity's owner.
        db: Database session.

    Returns:
        The max heart rate, or None when it cannot be derived.
    """
    user = users_integration.get_user(user_id, db)
    if user is None:
        return None
    return activity_streams_hr_zones.resolve_max_heart_rate(user.max_heart_rate, user.birthdate, user.timezone)


def _zones_of(
    samples: activity_streams_contracts.ParsedSamples,
    activity: activity_schema.ActivityRead,
    db: Session,
) -> activity_streams_hr_zones.HrZoneBreakdown | None:
    """Compute the heart-rate zone breakdown of an activity's samples.

    Zones are a function of the samples and the owner's *current* max heart rate (which itself follows their age), so
    they are computed per read rather than stored: a stored value is stale the moment the owner edits their profile or
    has a birthday.

    Args:
        samples: Every sample of the activity.
        activity: The parent activity, for its owner.
        db: Database session.

    Returns:
        The breakdown, or ``None`` when the samples have no heart rate, the activity has no owner or the owner's max
        heart rate is unknown.
    """
    if samples.heart_rate is None or activity.user_id is None:
        return None
    max_heart_rate = _max_heart_rate_of(activity.user_id, db)
    if not max_heart_rate:
        return None
    return activity_streams_hr_zones.compute_hr_zone_breakdown_sync(
        samples.offsets_ms, samples.heart_rate, max_heart_rate
    )


def _stored_samples_of(
    activity: activity_schema.ActivityRead, db: Session
) -> activity_streams_contracts.ParsedSamples | None:
    """Read an activity's samples.

    An activity stored before v0.22 has no samples row until the reprocess converts it, so its old waypoint streams
    are read and converted instead, without persisting the result.

    Args:
        activity: The parent activity.
        db: Database session.

    Returns:
        The samples, or ``None`` when the activity has none.
    """
    stored = activity_streams_crud.get_activity_samples(activity.id, db)
    if stored is not None:
        return stored
    if activity.start_time is None:
        return None
    return activity_streams_samples.samples_from_streams(
        activity_streams_crud.get_activity_streams(activity.id, db), activity.start_time
    )


def _serve(
    activity: activity_schema.ActivityRead,
    *,
    is_owner: bool,
    max_points: int | None,
    db: Session,
) -> activity_streams_schema.ActivitySamplesRead:
    """Build the streams of an activity as one viewer reads them.

    Args:
        activity: The parent activity, already readable by the viewer.
        is_owner: Whether the viewer owns the activity and so sees every channel.
        max_points: The most samples to return, or ``None`` for every sample.
        db: Database session.

    Returns:
        The streams: an empty timeline with every channel ``null`` when the activity has no samples.
    """
    hidden = set() if is_owner else {channel for channel in _SERVED_CHANNELS if _is_channel_hidden(activity, channel)}
    samples = _stored_samples_of(activity, db) or activity_streams_contracts.ParsedSamples(offsets_ms=[])
    zones = None if "heart_rate" in hidden else _zones_of(samples, activity, db)
    served = activity_streams_samples.downsample(samples, max_points) if max_points else samples

    channels: dict[str, list[float | None] | None] = {
        name: getattr(served, name) for name in activity_streams_constants.SAMPLE_CHANNELS
    }
    channels["pace"] = None if served.speed is None else activity_streams_samples.pace_from_speed(served.speed)
    return activity_streams_schema.ActivitySamplesRead(
        offsets_ms=served.offsets_ms,
        heart_rate_zones=zones,
        **{name: None if name in hidden else values for name, values in channels.items()},
    )


def get_activity_streams(
    activity_id: uuid.UUID,
    requester_user_id: uuid.UUID,
    db: Session,
    *,
    max_points: int | None = None,
) -> activity_streams_schema.ActivitySamplesRead:
    """Return an activity's streams for an authenticated caller, masked per channel.

    Args:
        activity_id: The parent activity.
        requester_user_id: The authenticated caller.
        db: Database session.
        max_points: The most samples to return, or ``None`` for every sample.

    Returns:
        The streams.

    Raises:
        NotFoundError: When the activity does not exist or is not visible to the caller, indistinguishable on purpose
            so the endpoint cannot be used to probe which activities exist.
    """
    activity = activity_integration.resolve_readable_parent(activity_id, requester_user_id, db)
    if activity is None:
        raise core_exceptions.NotFoundError("Activity not found")
    return _serve(activity, is_owner=requester_user_id == activity.user_id, max_points=max_points, db=db)


def get_public_activity_streams(
    activity_id: uuid.UUID,
    db: Session,
    *,
    max_points: int | None = None,
) -> activity_streams_schema.ActivitySamplesRead:
    """Return a publicly shared activity's streams, masked per channel.

    Args:
        activity_id: The parent activity.
        db: Database session.
        max_points: The most samples to return, or ``None`` for every sample.

    Returns:
        The streams.

    Raises:
        NotFoundError: When the activity is not publicly shareable, indistinguishable on purpose since this endpoint
            is unauthenticated.
    """
    activity = activity_integration.resolve_public_parent(activity_id, db)
    if activity is None:
        raise core_exceptions.NotFoundError("Activity not found")
    return _serve(activity, is_owner=False, max_points=max_points, db=db)
