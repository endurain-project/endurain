from pydantic import BaseModel

class Gear(BaseModel):
    id: int | None = None
    brand: str | None = None
    model: str | None = None
    nickname: str
    gear_type: int
    user_id: int | None = None
    created_at: str
    is_active: int | None = None
    strava_gear_id: str | None = None

    class Config:
        orm_mode = True