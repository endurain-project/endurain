"""Pydantic schemas for activity stream data."""

from enum import IntEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StrictInt,
    Tag,
    WithJsonSchema,
)

import core.pagination as core_pagination
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.hr_zones as activity_streams_hr_zones


class ActivityStreamsBase(BaseModel):
    """Schema for activity stream data.

    Attributes:
        id: Unique stream identifier.
        activity_id: Parent activity identifier.
        stream_type: Stream type code (1-8).
        stream_waypoints: Waypoint data points, as stored: JSON objects with a ``time`` and the stream's value key(s).
        strava_activity_stream_id: Strava stream ID.
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    activity_id: StrictInt
    stream_type: StrictInt
    stream_waypoints: list[dict[str, Any]]
    strava_activity_stream_id: StrictInt | None = None


class ActivityStreamZones(BaseModel):
    """A stream's zone breakdowns, by metric.

    Attributes:
        hr: The heart-rate zone breakdown.
    """

    hr: activity_streams_hr_zones.HrZoneBreakdown


class ActivityStreamsRead(ActivityStreamsBase):
    """A stored stream, as the services handle it before it is typed for a client.

    Its waypoints are the stored JSON objects. Routes answer with the typed
    :data:`ActivityStreamResponse` of the same stream.

    Attributes:
        id: Unique stream identifier.
        zone_percentages: The stream's zone breakdowns. Computed when the stream
            is served, from the owner's current thresholds; never stored, so it
            cannot go stale.
    """

    id: StrictInt
    zone_percentages: ActivityStreamZones | None = None


#: A number as it was stored: an integer stays an integer and a float a float, so the payload is served
#: unchanged. Declared a plain ``number`` in OpenAPI.
_Number = Annotated[float | int, WithJsonSchema({"type": "number"})]


class StreamWaypoint(BaseModel):
    """What every stream sample carries, served as it was stored.

    Attributes:
        time: When the sample was taken: a UTC ``YYYY-MM-DDTHH:MM:SS`` string, or seconds from the start for
            a stream imported from Strava. Absent when the activity hides its start time from the viewer.
    """

    model_config = ConfigDict(extra="allow")

    time: Annotated[str | _Number | None, Field(exclude_if=lambda value: value is None)] = None


class HeartRateWaypoint(StreamWaypoint):
    """A sample of the heart-rate stream.

    Attributes:
        hr: Heart rate in bpm.
    """

    hr: _Number | None = None


class PowerWaypoint(StreamWaypoint):
    """A sample of the power stream.

    Attributes:
        power: Power in watts.
    """

    power: _Number | None = None


class CadenceWaypoint(StreamWaypoint):
    """A sample of the cadence stream.

    Attributes:
        cad: Cadence in rpm (spm for running).
    """

    cad: _Number | None = None


class ElevationWaypoint(StreamWaypoint):
    """A sample of the elevation stream.

    Attributes:
        ele: Elevation in meters.
    """

    ele: _Number | None = None


class SpeedWaypoint(StreamWaypoint):
    """A sample of the speed stream.

    Attributes:
        vel: Speed in m/s.
    """

    vel: _Number | None = None


class PaceWaypoint(StreamWaypoint):
    """A sample of the pace stream.

    Attributes:
        pace: Pace in s/m; 0 where the speed is 0.
    """

    pace: _Number | None = None


class MapWaypoint(StreamWaypoint):
    """A GPS sample of the map stream.

    Attributes:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
    """

    lat: _Number | None = None
    lon: _Number | None = None


class TemperatureWaypoint(StreamWaypoint):
    """A sample of the temperature stream.

    Attributes:
        temp: Temperature in degrees Celsius.
    """

    temp: _Number | None = None


class ActivityStreamType(IntEnum):
    """The kind of data a stream holds; it fixes the shape of the stream's waypoints.

    Attributes:
        HEART_RATE: Heart rate; waypoints carry ``hr``.
        POWER: Power; waypoints carry ``power``.
        CADENCE: Cadence; waypoints carry ``cad``.
        ELEVATION: Elevation; waypoints carry ``ele``.
        SPEED: Speed; waypoints carry ``vel``.
        PACE: Pace; waypoints carry ``pace``.
        MAP: GPS position; waypoints carry ``lat`` and ``lon``.
        TEMPERATURE: Temperature; waypoints carry ``temp``.
    """

    HEART_RATE = activity_streams_constants.STREAM_TYPE_HR
    POWER = activity_streams_constants.STREAM_TYPE_POWER
    CADENCE = activity_streams_constants.STREAM_TYPE_CADENCE
    ELEVATION = activity_streams_constants.STREAM_TYPE_ELEVATION
    SPEED = activity_streams_constants.STREAM_TYPE_SPEED
    PACE = activity_streams_constants.STREAM_TYPE_PACE
    MAP = activity_streams_constants.STREAM_TYPE_MAP
    TEMPERATURE = activity_streams_constants.STREAM_TYPE_TEMPERATURE


class _ActivityStreamResponse[WaypointT: StreamWaypoint](BaseModel):
    """What every stream read answers with; the stream type fixes the waypoint shape.

    Attributes:
        activity_id: Parent activity identifier.
        stream_type: The kind of data the stream holds, which fixes the shape of its waypoints.
        stream_waypoints: The stream's samples.
        strava_activity_stream_id: Strava stream ID.
        id: Unique stream identifier.
        zone_percentages: The stream's zone breakdowns. Computed when the stream is served, from the owner's
            current thresholds; never stored, so it cannot go stale.
    """

    model_config = ConfigDict(extra="forbid")

    activity_id: StrictInt
    stream_type: ActivityStreamType
    stream_waypoints: list[WaypointT]
    strava_activity_stream_id: StrictInt | None = None
    id: StrictInt
    zone_percentages: ActivityStreamZones | None = None


class HeartRateStreamRead(_ActivityStreamResponse[HeartRateWaypoint]):
    """The heart-rate stream (type 1)."""


class PowerStreamRead(_ActivityStreamResponse[PowerWaypoint]):
    """The power stream (type 2)."""


class CadenceStreamRead(_ActivityStreamResponse[CadenceWaypoint]):
    """The cadence stream (type 3)."""


class ElevationStreamRead(_ActivityStreamResponse[ElevationWaypoint]):
    """The elevation stream (type 4)."""


class SpeedStreamRead(_ActivityStreamResponse[SpeedWaypoint]):
    """The speed stream (type 5)."""


class PaceStreamRead(_ActivityStreamResponse[PaceWaypoint]):
    """The pace stream (type 6)."""


class MapStreamRead(_ActivityStreamResponse[MapWaypoint]):
    """The GPS map stream (type 7)."""


class TemperatureStreamRead(_ActivityStreamResponse[TemperatureWaypoint]):
    """The temperature stream (type 8)."""


def _stream_tag(stream: object) -> str | None:
    """Name the stream class a value is validated as, from its ``stream_type``.

    Args:
        stream: A stream, as a mapping or as a model.

    Returns:
        The stream type as the tag of its class, or ``None`` when it has none.
    """
    stream_type = stream.get("stream_type") if isinstance(stream, dict) else getattr(stream, "stream_type", None)
    return None if stream_type is None else str(stream_type)


#: A stream as a client reads it: the shape of its waypoints follows its ``stream_type``. Tagged on the type, so
#: only the matching class validates it, and without an OpenAPI discriminator mapping, which clients read as
#: string keys although the type is an integer.
type ActivityStreamResponse = Annotated[
    Annotated[HeartRateStreamRead, Tag("1")]
    | Annotated[PowerStreamRead, Tag("2")]
    | Annotated[CadenceStreamRead, Tag("3")]
    | Annotated[ElevationStreamRead, Tag("4")]
    | Annotated[SpeedStreamRead, Tag("5")]
    | Annotated[PaceStreamRead, Tag("6")]
    | Annotated[MapStreamRead, Tag("7")]
    | Annotated[TemperatureStreamRead, Tag("8")],
    Discriminator(_stream_tag),
]

#: The envelope every activity child collection answers with. Streams are bounded
#: by the closed ``stream_type`` enum rather than by paging, but they carry the
#: same shape as laps, sets and workout steps so a client has one list contract
#: to implement instead of one per child resource.
ActivityStreamsPage = core_pagination.Page[ActivityStreamsRead]

#: The page a client reads: each stream typed by its ``stream_type``.
ActivityStreamResponsePage = core_pagination.Page[ActivityStreamResponse]
