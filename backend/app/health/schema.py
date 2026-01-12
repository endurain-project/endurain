from pydantic import BaseModel, ConfigDict, Field
from health.health_intraday_steps.schema import HealthIntradayStepsRead
from health.health_intraday_heart_rate.schema import HealthIntradayHeartrateRead


class HealthImportResponse(BaseModel):
    """
    Response model for listing health steps records.

    Attributes:
        created_intraday_step_records (list[HealthIntradayStepsRead]): List of health intraday steps records created.
        created_intraday_heart_rate_records (list[HealthIntradayHeartrateRead]): List of health intraday heart rate measurements created.
    """

    created_intraday_step_records:  list[HealthIntradayStepsRead] = Field(
        ..., description="Intraday steps created from the upload"
    )
    created_intraday_heart_rate_records:  list[HealthIntradayHeartrateRead] = Field(
        ..., description="Intraday heart rate measurements created from the upload"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
