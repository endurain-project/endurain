from pydantic import BaseModel


class ActivitySplits(BaseModel):
    id: int | None = None
    activity_id: int
    split_type: int
    total_elapsed_time: float | None = None
    total_timer_time: float | None = None
    total_distance: float | None = None
    avg_speed: float | None = None
    start_time: str
    total_ascent: int | None = None
    total_descent: int | None = None
    start_position_lat: float | None = None
    start_position_long: float | None = None
    end_position_lat: float | None = None
    end_position_long: float | None = None
    max_speed: float | None = None
    end_time: str
    total_calories: int | None = None
    start_elevation: int | None = None

    class Config:
        orm_mode = True
