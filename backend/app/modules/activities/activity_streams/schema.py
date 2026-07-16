"""Pydantic schemas for activity stream data."""

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictInt,
)


class ActivityStreamsBase(BaseModel):
    """
    Schema for activity stream data.

    Attributes:
        id: Unique stream identifier.
        activity_id: Parent activity identifier.
        stream_type: Stream type code (1-7).
        stream_waypoints: Waypoint data points.
        strava_activity_stream_id: Strava stream ID.
        zone_percentages: Zone breakdowns keyed by metric (e.g. 'hr').
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    activity_id: StrictInt
    stream_type: StrictInt
    stream_waypoints: list[dict]
    strava_activity_stream_id: StrictInt | None = None
    zone_percentages: dict | None = None


class ActivityStreamsCreate(ActivityStreamsBase):
    """
    Schema for activity stream creation.

    Inherits all fields from ActivityStreamsBase.
    """


class ActivityStreamsRead(ActivityStreamsBase):
    """
    Schema for activity stream reading.

    Attributes:
        id: Unique stream identifier.
    """

    id: StrictInt
