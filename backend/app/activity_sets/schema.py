from pydantic import BaseModel


class ActivitySets(BaseModel):
    id: int | None = None
    activity_id: int
    duration: float
    repetitions: int | None
    weight: float | None
    set_type: str
    start_time: str

    class Config:
        orm_mode = True
