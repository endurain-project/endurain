from pydantic import BaseModel, ConfigDict
from datetime import date as datetime_date


class HealthSteps(BaseModel):
    id: int | None = None
    user_id: int | None = None
    date: datetime_date | None = None
    steps: int | None = None

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )
