"""Constants for activity stream types."""

from core.stored_enum import StoredStrEnum


class ActivityStreamType(StoredStrEnum):
    """The kind of data a stream holds, which fixes the shape of the stream's waypoints.

    ``stored`` is the integer in ``activity_streams.stream_type``.

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

    HEART_RATE = ("heart_rate", 1)
    POWER = ("power", 2)
    CADENCE = ("cadence", 3)
    ELEVATION = ("elevation", 4)
    SPEED = ("speed", 5)
    PACE = ("pace", 6)
    MAP = ("map", 7)
    TEMPERATURE = ("temperature", 8)


STREAM_TYPE_HR: int = ActivityStreamType.HEART_RATE.stored
STREAM_TYPE_POWER: int = ActivityStreamType.POWER.stored
STREAM_TYPE_CADENCE: int = ActivityStreamType.CADENCE.stored
STREAM_TYPE_ELEVATION: int = ActivityStreamType.ELEVATION.stored
STREAM_TYPE_SPEED: int = ActivityStreamType.SPEED.stored
STREAM_TYPE_PACE: int = ActivityStreamType.PACE.stored
STREAM_TYPE_MAP: int = ActivityStreamType.MAP.stored
STREAM_TYPE_TEMPERATURE: int = ActivityStreamType.TEMPERATURE.stored
