from pydantic import BaseModel


class HealthData(BaseModel):
    id: int | None = None
    user_id: int | None = None
    created_at: str | None = None
    weight: float | None = None

    class Config:
        orm_mode = True