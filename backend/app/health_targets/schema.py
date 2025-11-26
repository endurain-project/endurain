from pydantic import BaseModel, ConfigDict


class HealthTargets(BaseModel):
    id: int | None = None
    user_id: int | None = None
    weight: float | None = None
    steps: int | None = None
    sleep: int | None = None

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )
