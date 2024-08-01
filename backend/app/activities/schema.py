from pydantic import BaseModel


class Activity(BaseModel):
    id: int | None = None
    user_id: int | None = None
    description: str | None = None
    distance: int
    name: str
    activity_type: int
    start_time: str
    end_time: str
    city: str | None = None
    town: str | None = None
    country: str | None = None
    created_at: str | None = None
    elevation_gain: int
    elevation_loss: int
    pace: float
    average_speed: float
    average_power: int
    calories: int | None = None
    visibility: int | None = None
    gear_id: int | None = None
    strava_gear_id: str | None = None
    strava_activity_id: int | None = None

    class Config:
        orm_mode = True


class ActivityDistances(BaseModel):
    swim: float
    bike: float
    run: float


class ActivityEdit(BaseModel):
    id: int
    description: str | None = None
    name: str
    activity_type: int
    visibility: int | None = None