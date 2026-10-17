"""Pydantic schemas for activity stream data."""

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictInt,
)

import core.pagination as core_pagination


class ActivityStreamsBase(BaseModel):
    """Schema for activity stream data.

    Attributes:
        id: Unique stream identifier.
        activity_id: Parent activity identifier.
        stream_type: Stream type code (1-7).
        stream_waypoints: Waypoint data points.
        strava_activity_stream_id: Strava stream ID.
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )

    activity_id: StrictInt
    stream_type: StrictInt
    stream_waypoints: list[dict]
    strava_activity_stream_id: StrictInt | None = None


class ActivityStreamsRead(ActivityStreamsBase):
    """Schema for activity stream reading.

    Attributes:
        id: Unique stream identifier.
        zone_percentages: Zone breakdowns keyed by metric (e.g. 'hr'). Computed
            when the stream is served, from the owner's current thresholds; never
            stored, so it cannot go stale.
    """

    id: StrictInt
    zone_percentages: dict | None = None


#: The envelope every activity child collection answers with. Streams are bounded
#: by the closed ``stream_type`` enum rather than by paging, but they carry the
#: same shape as laps, sets and workout steps so a client has one list contract
#: to implement instead of one per child resource.
ActivityStreamsPage = core_pagination.Page[ActivityStreamsRead]
