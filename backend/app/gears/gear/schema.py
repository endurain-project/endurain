from pydantic import BaseModel


class Gear(BaseModel):
    id: int | None = None
    brand: str | None = None
    model: str | None = None
    nickname: str
    gear_type: int
    user_id: int | None = None
    created_at: str | None = None
    active: bool | None = None
    initial_kms: float | None = None
    purchase_value: float | None = None
    strava_gear_id: str | None = None
    garminconnect_gear_id: str | None = None
    serial_number: str | None = None
    computer_model_id: int | None = None

    model_config = {"from_attributes": True}