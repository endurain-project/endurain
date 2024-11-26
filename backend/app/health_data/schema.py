from pydantic import BaseModel
from datetime import date

class HealthData(BaseModel):
    id: int | None = None
    user_id: int | None = None
    created_at: date | None = None
    weight: float | None = None
    bmi: float | None = None
    body_fat: float | None = None
    body_water: float | None = None
    bone_mass: float | None = None
    muscle_mass: float | None = None
    physique_rating: float | None = None
    visceral_fat: float | None = None
    metabolic_age: float | None = None

    class Config:
        orm_mode = True