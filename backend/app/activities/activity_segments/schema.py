from pydantic import BaseModel
from typing import List, Tuple
from datetime import datetime

class ActivitySegment(BaseModel):
    id: int | None = None
    activity_id: int | None = None
    segment_id: int | None = None
    segment_name: str | None = None
    start_time: datetime | None = None
    gate_ordered: List[int] | None = None
    gps_point_index_ordered: List[Tuple[int, int]] | None = None
    sub_segment_times: List[list[Tuple[int,float]]] | None = None
    segment_times: List[float] | None = None

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