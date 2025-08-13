from pydantic import BaseModel
from typing import List, Tuple
from datetime import datetime

class ActivitySegment(BaseModel):
    id: int | None = None
    activity_id: int | None = None
    segment_id: int | None = None
    lap_number: int | None = None
    segment_name: str | None = None
    start_time: datetime | None = None
    segment_ele_gain: int | None = None
    segment_ele_loss: int | None = None
    segment_pace: float | None = None
    segment_hr_avg: int | None = None
    segment_hr_max: int | None = None
    segment_distance: int | None = None
    segment_time: float | None = None
    gate_ordered: List[int] | None = None
    gps_point_index_ordered: List[Tuple[int, int]] | None = None
    sub_segment_times: list[float] | None = None
    sub_segment_paces: List[float] | None = None
    gate_times: List[datetime] | None = None
    sub_segment_distances: List[float] | None = None
    stream_latlon: List[dict] | None = None
    stream_ele: List[dict] | None = None

    class Config:
        orm_mode = True

class Segments(BaseModel):
    id: int | None = None
    user_id: int | None = None
    name: str | None = None
    activity_type: int | None = None
    gates: List[List] | None = None
    city: str | None = None
    town: str | None = None
    country: str | None = None
    num_activities: int | None = None
    most_recent_activity: datetime | None = None

    class Config:
        orm_mode=True