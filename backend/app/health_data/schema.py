from pydantic import BaseModel
from datetime import date as datetime_date


class HealthData(BaseModel):
    id: int | None = None
    user_id: int | None = None
    date: datetime_date | None = None
    weight: float | None = None
    bmi: float | None = None
    body_fat: float | None = None
    body_water: float | None = None
    bone_mass: float | None = None
    muscle_mass: float | None = None
    physique_rating: int | None = None
    visceral_fat: float | None = None
    metabolic_age: int | None = None
    garminconnect_body_composition_id: str | None = None

    model_config = {"from_attributes": True}
