"""Pydantic schemas for activity stream data."""

import uuid
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
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
        stream_type: Stream type code, as stored (1-8); a client reads it as ``ActivityStreamType``.
        stream_waypoints: Waypoint data points, as stored: JSON objects with a ``time`` and the stream's value key(s).
        strava_activity_stream_id: Strava stream ID.
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    activity_id: uuid.UUID
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

    id: uuid.UUID
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

    time: Annotated[
        str | _Number | None,
        Field(
            exclude_if=lambda value: value is None,
            description="When the sample was taken: a UTC timestamp, or seconds from the start for a Strava stream",
        ),
    ] = None


class HeartRateWaypoint(StreamWaypoint):
    """A sample of the heart-rate stream.

    Attributes:
        hr: Heart rate in bpm.
    """

    hr: _Number | None = Field(default=None, description="Heart rate in beats per minute")


class PowerWaypoint(StreamWaypoint):
    """A sample of the power stream.

    Attributes:
        power: Power in watts.
    """

    power: _Number | None = Field(default=None, description="Power in watts")


class CadenceWaypoint(StreamWaypoint):
    """A sample of the cadence stream.

    Attributes:
        cad: Cadence in rpm (spm for running).
    """

    cad: _Number | None = Field(
        default=None, description="Cadence in revolutions per minute (steps per minute for running)"
    )


class ElevationWaypoint(StreamWaypoint):
    """A sample of the elevation stream.

    Attributes:
        ele: Elevation in meters.
    """

    ele: _Number | None = Field(default=None, description="Elevation in meters")


class SpeedWaypoint(StreamWaypoint):
    """A sample of the speed stream.

    Attributes:
        vel: Speed in m/s.
    """

    vel: _Number | None = Field(default=None, description="Speed in meters per second")


class PaceWaypoint(StreamWaypoint):
    """A sample of the pace stream.

    Attributes:
        pace: Pace in s/m; 0 where the speed is 0.
    """

    pace: _Number | None = Field(default=None, description="Pace in seconds per meter; 0 where the speed is 0")


class MapWaypoint(StreamWaypoint):
    """A GPS sample of the map stream.

    Attributes:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
    """

    lat: _Number | None = Field(default=None, description="Latitude in decimal degrees")
    lon: _Number | None = Field(default=None, description="Longitude in decimal degrees")


class TemperatureWaypoint(StreamWaypoint):
    """A sample of the temperature stream.

    Attributes:
        temp: Temperature in degrees Celsius.
    """

    temp: _Number | None = Field(default=None, description="Temperature in degrees Celsius")


#: The stream type a response carries, built from the stored integer the services handle.
StoredStreamType = Annotated[
    activity_streams_constants.ActivityStreamType,
    BeforeValidator(activity_streams_constants.ActivityStreamType.accept_stored),
]


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

    activity_id: uuid.UUID
    stream_type: StoredStreamType
    stream_waypoints: list[WaypointT]
    strava_activity_stream_id: StrictInt | None = None
    id: uuid.UUID
    zone_percentages: ActivityStreamZones | None = None


class HeartRateStreamRead(_ActivityStreamResponse[HeartRateWaypoint]):
    """The heart-rate stream (`heart_rate`)."""


class PowerStreamRead(_ActivityStreamResponse[PowerWaypoint]):
    """The power stream (`power`)."""


class CadenceStreamRead(_ActivityStreamResponse[CadenceWaypoint]):
    """The cadence stream (`cadence`)."""


class ElevationStreamRead(_ActivityStreamResponse[ElevationWaypoint]):
    """The elevation stream (`elevation`)."""


class SpeedStreamRead(_ActivityStreamResponse[SpeedWaypoint]):
    """The speed stream (`speed`)."""


class PaceStreamRead(_ActivityStreamResponse[PaceWaypoint]):
    """The pace stream (`pace`)."""


class MapStreamRead(_ActivityStreamResponse[MapWaypoint]):
    """The GPS map stream (`map`)."""


class TemperatureStreamRead(_ActivityStreamResponse[TemperatureWaypoint]):
    """The temperature stream (`temperature`)."""


def _stream_tag(stream: object) -> str | None:
    """Name the stream class a value is validated as, from its ``stream_type``.

    Args:
        stream: A stream, as a mapping or as a model.

    Returns:
        The stream type as the tag of its class, or ``None`` when it has none.
    """
    stream_type = stream.get("stream_type") if isinstance(stream, dict) else getattr(stream, "stream_type", None)
    return (
        None if stream_type is None else str(activity_streams_constants.ActivityStreamType.accept_stored(stream_type))
    )


#: A stream as a client reads it: the shape of its waypoints follows its ``stream_type``. Tagged on the type, so
#: only the matching class validates it, and without an OpenAPI discriminator mapping, which clients read as
#: numeric keys although the type is stored as an integer.
type ActivityStreamResponse = Annotated[
    Annotated[HeartRateStreamRead, Tag(activity_streams_constants.ActivityStreamType.HEART_RATE.value)]
    | Annotated[PowerStreamRead, Tag(activity_streams_constants.ActivityStreamType.POWER.value)]
    | Annotated[CadenceStreamRead, Tag(activity_streams_constants.ActivityStreamType.CADENCE.value)]
    | Annotated[ElevationStreamRead, Tag(activity_streams_constants.ActivityStreamType.ELEVATION.value)]
    | Annotated[SpeedStreamRead, Tag(activity_streams_constants.ActivityStreamType.SPEED.value)]
    | Annotated[PaceStreamRead, Tag(activity_streams_constants.ActivityStreamType.PACE.value)]
    | Annotated[MapStreamRead, Tag(activity_streams_constants.ActivityStreamType.MAP.value)]
    | Annotated[TemperatureStreamRead, Tag(activity_streams_constants.ActivityStreamType.TEMPERATURE.value)],
    Discriminator(_stream_tag),
]

#: The envelope every activity child collection answers with. Streams are bounded
#: by the closed ``stream_type`` enum rather than by paging, but they carry the
#: same shape as laps, sets and workout steps so a client has one list contract
#: to implement instead of one per child resource.
ActivityStreamsPage = core_pagination.Page[ActivityStreamsRead]

#: The page a client reads: each stream typed by its ``stream_type``.
ActivityStreamResponsePage = core_pagination.Page[ActivityStreamResponse]
