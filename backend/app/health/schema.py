from pydantic import BaseModel, ConfigDict, Field
from health_intraday_steps.schema import HealthIntradayStepsCreate
from health_intraday_heart_rate.schema import HealthIntradayHeartrateBase


class HealthImportResponse(BaseModel):
    """
    Response model for listing health steps records.

    Attributes:
        total (StrictInt): Total number of steps records for the user.
        num_records (StrictInt | None): Number of records in this response.
        page_number (StrictInt | None): Current page number.
        records (list[HealthStepsRead]): List of health steps records.
    """

    created_intraday_step_records:  list[HealthIntradayStepsCreate] = Field(
        ..., description="Intraday steps created from the upload"
    )
    created_heart_rate_records:  list[HealthIntradayHeartrateBase] = Field(
        ..., description="Intraday heart rate measurements created from the upload"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
