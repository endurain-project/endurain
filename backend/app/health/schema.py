from pydantic import BaseModel, ConfigDict, Field
from health.health_intraday_steps.schema import HealthIntradayStepsRead
from health.health_intraday_heart_rate.schema import HealthIntradayHeartrateRead
from health.health_sleep.schema import HealthSleepRead
from health.health_steps.schema import HealthStepsRead


class HealthImportResponse(BaseModel):
    """
    Response model for listing health steps records.

    Attributes:
        created_intraday_step_records (list[HealthIntradayStepsRead]): List of health intraday steps records created.
        created_intraday_heart_rate_records (list[HealthIntradayHeartrateRead]): List of health intraday heart rate measurements created.
        updated_sleep (HealthSleepRead): Updates daily sleep record.
    """

    created_intraday_step_records:  list[HealthIntradayStepsRead] = Field(
        ..., description="Intraday steps created from the upload"
    )
    created_intraday_heart_rate_records:  list[HealthIntradayHeartrateRead] = Field(
        ..., description="Intraday heart rate measurements created from the upload"
    )
    updated_sleep:  HealthSleepRead  | None = Field(
        ..., description="Health sleep stats updated from the upload"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
