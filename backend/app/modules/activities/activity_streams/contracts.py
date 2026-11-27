"""Package-owned internal data shapes for activity streams.

Separate from ``schema.py`` (the client-facing stream payloads) because these
never reach a client. They carry parser output into generic activity ingestion.
The waypoint shapes are the series a parser's analysis reads.
"""

from dataclasses import dataclass
from typing import TypedDict

import modules.activities.activity_streams.constants as activity_streams_constants


class TimedWaypoint(TypedDict):
    """The key every stream sample carries.

    Attributes:
        time: UTC timestamp of the sample, as ``YYYY-MM-DDTHH:MM:SS``.
    """

    time: str


class ElevationWaypoint(TimedWaypoint):
    """A sample of the elevation stream.

    Attributes:
        ele: Elevation in meters.
    """

    ele: float


@dataclass(frozen=True)
class ParsedSamples:
    """The columnar time series of an activity, before its parent activity identifier is assigned.

    Every channel is aligned with ``offsets_ms``; a channel is ``None`` when the activity has none, and an element is
    ``None`` where a sample has no value. Latitude and longitude are both present or both absent.

    Attributes:
        offsets_ms: Each sample's time in milliseconds from the activity's start time; may be negative.
        latitude: Latitude per sample, in degrees.
        longitude: Longitude per sample, in degrees.
        elevation: Elevation per sample, in meters.
        heart_rate: Heart rate per sample, in bpm.
        power: Power per sample, in watts.
        cadence: Cadence per sample, in rpm (spm for running).
        speed: Speed per sample, in m/s.
        temperature: Temperature per sample, in degrees Celsius.
    """

    offsets_ms: list[int]
    latitude: list[float | None] | None = None
    longitude: list[float | None] | None = None
    elevation: list[float | None] | None = None
    heart_rate: list[float | None] | None = None
    power: list[float | None] | None = None
    cadence: list[float | None] | None = None
    speed: list[float | None] | None = None
    temperature: list[float | None] | None = None

    def __post_init__(self) -> None:
        """Check that every present channel matches ``offsets_ms`` and that latitude and longitude come together.

        Raises:
            ValueError: A channel's length differs from ``offsets_ms``, or only one of latitude and longitude is set.
        """
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must both be present or both be absent")
        for name in activity_streams_constants.SAMPLE_CHANNELS:
            channel = getattr(self, name)
            if channel is not None and len(channel) != len(self.offsets_ms):
                raise ValueError(f"{name} has {len(channel)} samples, offsets_ms has {len(self.offsets_ms)}")
