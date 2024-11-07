from pydantic import BaseModel


class HealthTargets(BaseModel):
    id: int | None = None
    user_id: int | None = None
    weight: float | None = None

    class Config:
        orm_mode = True