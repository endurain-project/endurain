"""ORM↔schema transformation and visibility masking for activity streams.

The counterpart of :mod:`modules.activities.activity.serializers`, and named to
match: ``crud`` calls the transformation at its edges so ORM rows never leave the
persistence layer, and the service applies the masking.

Masking is per stream *type* rather than one hide flag, which is why the streams
package does its own filtering instead of using the shared child-collection read:
an activity can hide its heart rate while still publishing its route.
"""

from typing import overload

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.models as activity_streams_models
import modules.activities.activity_streams.schema as activity_streams_schema

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


def is_stream_hidden(
    activity: activity_schema.Activity,
    stream_type: int,
) -> bool:
    """
    Check if a stream type is hidden.

    Args:
        activity: The activity schema instance.
        stream_type: The stream type constant.

    Returns:
        True if the stream should be hidden.
    """
    attr = _STREAM_HIDE_MAP.get(stream_type)
    return bool(attr and getattr(activity, attr, False))


def filter_visible_streams(
    streams: list[activity_streams_schema.ActivityStreamsRead],
    activity: activity_schema.Activity,
) -> list[activity_streams_schema.ActivityStreamsRead]:
    """
    Filter out streams hidden by the activity.

    Args:
        streams: The activity's streams, as read schemas.
        activity: The activity schema instance.

    Returns:
        Streams that are not hidden.
    """
    return [s for s in streams if not is_stream_hidden(activity, s.stream_type)]


@overload
def transform_activity_streams(
    activity_streams: list[activity_streams_models.ActivityStreams],
) -> list[activity_streams_schema.ActivityStreamsRead]: ...


@overload
def transform_activity_streams(
    activity_streams: activity_streams_models.ActivityStreams,
) -> activity_streams_schema.ActivityStreamsRead: ...


def transform_activity_streams(
    activity_streams: activity_streams_models.ActivityStreams | list[activity_streams_models.ActivityStreams],
) -> activity_streams_schema.ActivityStreamsRead | list[activity_streams_schema.ActivityStreamsRead]:
    """
    Transform a stream or list of streams to a Pydantic schema or list of schemas.

    Args:
        activity_streams: The stream ORM instance or list of stream ORM instances.

    Returns:
        The activity stream as a schema or list of schemas.
    """
    if isinstance(activity_streams, list):
        return [activity_streams_schema.ActivityStreamsRead.model_validate(stream) for stream in activity_streams]
    return activity_streams_schema.ActivityStreamsRead.model_validate(activity_streams)
