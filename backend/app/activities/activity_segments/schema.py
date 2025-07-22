from pydantic import BaseModel
from typing import List, Tuple
from datetime import datetime

class Intersection(BaseModel):
    segment_name: str
    gate_ordered: List[int]
    gps_point_index_ordered: List[Tuple[int, int]]
    sub_segment_times: List[list[Tuple[int,float]]] | None = None
    segment_times: List[float] | None = None
    gate_times: List[List[Tuple[int, datetime]]] | None = None

class Segment(BaseModel):
    id: int | None = None
    user_id: int | None = None
    name: str | None = None
    activity_type: int | None = None
    gates: List[List] | None = None

    class Config:
        orm_mode=True