from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
)


class HealthListResponse(BaseModel):
    """
    Response model for listing records.

    Attributes:
        total: Total number of health records for the user.
        num_records: Number of records in this response.
        page_number: Current page number.
    """

    total: StrictInt = Field(
        ...,
        description="Total number of health records for the user",
    )
    num_records: StrictInt | None = Field(
        default=None,
        description="Number of records in this response",
    )
    page_number: StrictInt | None = Field(
        default=None,
        description="Current page number",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthSleepDashboard(BaseModel):
    """
    Latest sleep metrics for dashboard display.

    Attributes:
        total_sleep_seconds: Total sleep duration in seconds.
        resting_heart_rate: Resting heart rate in bpm.
        hrv_status: Heart rate variability status.
        avg_skin_temp_deviation: Skin temp deviation in celsius.
    """

    total_sleep_seconds: StrictInt | None = Field(
        default=None,
        description="Total sleep duration in seconds",
    )
    resting_heart_rate: StrictInt | None = Field(
        default=None,
        description="Resting heart rate in bpm",
    )
    hrv_status: str | None = Field(
        default=None,
        description="Heart rate variability status",
    )
    avg_skin_temp_deviation: StrictFloat | None = Field(
        default=None,
        description="Average skin temperature deviation",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthWeightDashboard(BaseModel):
    """
    Latest weight metrics for dashboard display.

    Attributes:
        weight: Weight in kilograms.
        bmi: Body Mass Index.
    """

    weight: StrictFloat | None = Field(
        default=None,
        description="Weight in kilograms",
    )
    bmi: StrictFloat | None = Field(
        default=None,
        description="Body Mass Index",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthStepsDashboard(BaseModel):
    """
    Latest steps for dashboard display.

    Attributes:
        steps: Number of steps taken.
    """

    steps: StrictInt | None = Field(
        default=None,
        description="Number of steps taken",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthFastingDashboard(BaseModel):
    """
    Active or latest fasting session for dashboard display.

    Attributes:
        id: Unique identifier for the fasting record.
        fast_start_time: Start time of fast.
        fast_end_time: End time of fast (null if ongoing).
        status: Current status of the fasting session.
        actual_duration_seconds: Actual fasting duration in seconds.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier for the fasting record",
    )
    fast_start_time: datetime = Field(
        ...,
        description="Start time of fast",
    )
    fast_end_time: datetime | None = Field(
        default=None,
        description="End time of fast (null if ongoing)",
    )
    status: str = Field(
        ...,
        description="Current status of the fasting session",
    )
    actual_duration_seconds: StrictInt | None = Field(
        default=None,
        description="Actual fasting duration in seconds",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthWaterDashboard(BaseModel):
    """
    Today's water intake for dashboard display.

    Attributes:
        amount_ml: Total water consumed today in milliliters.
    """

    amount_ml: StrictFloat | None = Field(
        default=None,
        description="Total water consumed today in ml",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthPoopDashboard(BaseModel):
    """
    Today's bowel movement summary for dashboard display.

    Attributes:
        count: Number of bowel movements recorded today.
    """

    count: StrictInt = Field(
        ...,
        description="Number of bowel movements recorded today",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class HealthDashboardResponse(BaseModel):
    """
    Consolidated dashboard response with current health metrics.

    Attributes:
        sleep: Latest sleep data.
        weight: Latest weight data.
        steps: Today's step count.
        fasting: Active or most recent fasting session.
        water: Today's water intake.
        poop: Today's bowel movement summary.
    """

    sleep: HealthSleepDashboard | None = Field(
        default=None,
        description="Latest sleep metrics",
    )
    weight: HealthWeightDashboard | None = Field(
        default=None,
        description="Latest weight metrics",
    )
    steps: HealthStepsDashboard | None = Field(
        default=None,
        description="Latest steps data",
    )
    fasting: HealthFastingDashboard | None = Field(
        default=None,
        description="Active or latest fasting session",
    )
    water: HealthWaterDashboard | None = Field(
        default=None,
        description="Today's water intake",
    )
    poop: HealthPoopDashboard | None = Field(
        default=None,
        description="Today's bowel movement summary",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
