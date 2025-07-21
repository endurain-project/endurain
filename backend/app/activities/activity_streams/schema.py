from pydantic import BaseModel
from typing import List


class ActivityStreams(BaseModel):
    """
    Represents a stream of activity data associated with an activity.

    Attributes:
        id (int | None): Unique identifier for the activity stream (optional).
        activity_id (int): Identifier of the related activity.
        stream_type (int): Type of the stream (e.g., GPS, heart rate, etc.).
        stream_waypoints (List[dict]): List of waypoints or data points in the stream.
        strava_activity_stream_id (int | None): Identifier for the corresponding Strava activity stream (optional).
        hr_zone_percentages (dict | None): Heart rate zone percentages for the activity (optional).
    """

    id: int | None = None
    activity_id: int
    stream_type: int
    stream_waypoints: List[dict]
    strava_activity_stream_id: int | None = None
    hr_zone_percentages: dict | None = None

    model_config = {"from_attributes": True}
