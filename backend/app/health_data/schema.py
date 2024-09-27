from pydantic import BaseModel
from datetime import date

class HealthData(BaseModel):
    id: int | None = None
    user_id: int | None = None
    created_at: date | None = None
    weight: float | None = None

    class Config:
        orm_mode = True