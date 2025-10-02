from pydantic import BaseModel

class Gear(BaseModel):
    id: int | None = None
    brand: str | None = None
    model: str | None = None
    nickname: str
    gear_type: int
    user_id: int | None = None
    created_at: str | None = None
    is_active: int | None = None
    initial_kms: float | None = None
    purchase_value: float | None = None
    strava_gear_id: str | None = None
    garminconnect_gear_id: str | None = None

    model_config = {
        "from_attributes": True
    }