"""Pydantic schemas for activity stream data."""

import uuid
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.hr_zones as activity_streams_hr_zones


class ActivityStreamsBase(BaseModel):
    """Schema for a stream stored before the columnar samples.

    Attributes:
        id: Unique stream identifier.
        activity_id: Parent activity identifier.
        stream_type: Stream type code, as stored (1-8).
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


class ActivityStreamsRead(ActivityStreamsBase):
    """A stored stream, as the services handle it.

    Attributes:
        id: Unique stream identifier.
    """

    id: uuid.UUID


class ActivitySamplesRead(BaseModel):
    """An activity's streams: its samples on one timeline, one list per channel, all aligned with ``offsets_ms``.

    A channel is ``null`` when the activity has none or hides it from the viewer, and an element is ``null`` where a
    sample has no value.

    Attributes:
        offsets_ms: Each sample's time in milliseconds from the activity start; empty when the activity has no
            samples.
        latitude: Latitude per sample, in degrees.
        longitude: Longitude per sample, in degrees.
        elevation: Elevation per sample, in meters.
        heart_rate: Heart rate per sample, in beats per minute.
        power: Power per sample, in watts.
        cadence: Cadence per sample, in revolutions per minute (steps per minute for running).
        speed: Speed per sample, in meters per second.
        pace: Pace per sample, in seconds per meter, derived from the speed; ``null`` where the speed is not above 0.
        temperature: Temperature per sample, in degrees Celsius.
        heart_rate_zones: The time in each heart-rate zone, computed from the owner's current thresholds and every
            sample, never stored; ``null`` when there is no heart-rate time or the heart rate is hidden.
    """

    model_config = ConfigDict(extra="forbid")

    offsets_ms: list[int] = Field(
        description="Each sample's time in milliseconds from the activity start; empty when there are no samples"
    )
    latitude: list[float | None] | None = Field(description="Latitude per sample in degrees")
    longitude: list[float | None] | None = Field(description="Longitude per sample in degrees")
    elevation: list[float | None] | None = Field(description="Elevation per sample in meters")
    heart_rate: list[float | None] | None = Field(description="Heart rate per sample in beats per minute")
    power: list[float | None] | None = Field(description="Power per sample in watts")
    cadence: list[float | None] | None = Field(
        description="Cadence per sample in revolutions per minute (steps per minute for running)"
    )
    speed: list[float | None] | None = Field(description="Speed per sample in meters per second")
    pace: list[float | None] | None = Field(
        description="Pace per sample in seconds per meter, derived from the speed; null where the speed is not above 0"
    )
    temperature: list[float | None] | None = Field(description="Temperature per sample in degrees Celsius")
    heart_rate_zones: activity_streams_hr_zones.HrZoneBreakdown | None = Field(
        description="Time in each heart-rate zone, from the owner's current thresholds; null when there is none"
    )


class ActivitySamplesArchive(BaseModel):
    """An activity's samples as a profile archive carries them.

    Attributes:
        activity_id: The activity the samples belong to, as keyed in the archive.
        offsets_ms: Each sample's time in milliseconds from the activity start time.
        latitude: Latitude per sample, in degrees.
        longitude: Longitude per sample, in degrees.
        elevation: Elevation per sample, in meters.
        heart_rate: Heart rate per sample, in beats per minute.
        power: Power per sample, in watts.
        cadence: Cadence per sample, in revolutions per minute (steps per minute for running).
        speed: Speed per sample, in meters per second.
        temperature: Temperature per sample, in degrees Celsius.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    activity_id: uuid.UUID
    offsets_ms: list[int]
    latitude: list[float | None] | None = None
    longitude: list[float | None] | None = None
    elevation: list[float | None] | None = None
    heart_rate: list[float | None] | None = None
    power: list[float | None] | None = None
    cadence: list[float | None] | None = None
    speed: list[float | None] | None = None
    temperature: list[float | None] | None = None

    @model_validator(mode="after")
    def _channels_match_the_timeline(self) -> Self:
        """Check that every channel is aligned with ``offsets_ms`` and that the position comes whole.

        Returns:
            The record.

        Raises:
            ValueError: A channel's length differs from ``offsets_ms``, or only one of latitude and longitude is set.
        """
        self.to_samples()
        return self

    def to_samples(self) -> activity_streams_contracts.ParsedSamples:
        """Return the record's samples without the activity key.

        Returns:
            The samples.
        """
        return activity_streams_contracts.ParsedSamples(**self.model_dump(exclude={"activity_id"}))
