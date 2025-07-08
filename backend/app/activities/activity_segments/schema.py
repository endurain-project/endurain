from pydantic import BaseModel
from typing import List

class Segment(BaseModel):
    id: int | None = None
    user_id: int | None = None
    name: str | None = None
    activity_type: int | None = None
    splits: List[List] | None = None

    class Config:
        orm_mode=True