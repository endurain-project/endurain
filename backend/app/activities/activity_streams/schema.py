from pydantic import BaseModel
from typing import List


class ActivityStreams(BaseModel):
    id: int | None = None
    activity_id: int
    stream_type: int
    stream_waypoints: List[dict]
    strava_activity_stream_id: int | None = None

    class Config:
        orm_mode = True