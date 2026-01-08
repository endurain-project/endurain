from enum import Enum
from pydantic import (
    BaseModel,
    ConfigDict,
    model_validator,
    StrictInt,
    StrictStr,
    Field,
)
from datetime import datetime, date as datetime_date
from decimal import Decimal


class Source(Enum):
    """
    An enumeration representing supported sources.

    Members:
        GARMIN: Garmin health data source
    """

    GARMIN = "garmin"


class SleepStageType(Enum):
    """
    An enumeration representing sleep stage types.

    Members:
        DEEP: Deep sleep stage
        LIGHT: Light sleep stage
        REM: REM (Rapid Eye Movement) sleep stage
        AWAKE: Awake periods during sleep
    """

    DEEP = 0
    LIGHT = 1
    REM = 2
    AWAKE = 3


class HRVStatus(Enum):
    """
    Enum representing the status of Heart Rate Variability (HRV).

    This enum defines the possible HRV status values that can be associated with
    sleep or health data.

    Attributes:
        BALANCED: Indicates optimal HRV, suggesting good recovery and readiness.
        UNBALANCED: Indicates HRV is outside the normal range, suggesting stress or incomplete recovery.
        LOW: Indicates HRV is lower than normal, suggesting fatigue or increased stress.
        POOR: Indicates significantly low HRV, suggesting poor recovery or health concerns.
    """

    BALANCED = "BALANCED"
    UNBALANCED = "UNBALANCED"
    LOW = "LOW"
    POOR = "POOR"


class SleepScore(Enum):
    """
    Enum representing sleep score categories.

    This enum defines the possible sleep score categories based on sleep quality.

    Attributes:
        EXCELLENT: Indicates excellent sleep quality 90-100.
        GOOD: Indicates good sleep quality ~70-89.
        FAIR: Indicates fair sleep quality ~50-69.
        POOR: Indicates poor sleep quality <50.
    """

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class HealthSleepStage(BaseModel):
    """
    Represents individual sleep stage interval.

    Attributes:
        stage_type: Type of sleep stage.
        start_time_gmt: Start time of the stage in GMT.
        end_time_gmt: End time of the stage in GMT.
        duration_seconds: Duration of the stage in seconds.
    """

    stage_type: SleepStageType | None = Field(None, description="Type of sleep stage")
    start_time_gmt: datetime | None = Field(
        None, description="Start time of the stage in GMT"
    )
    end_time_gmt: datetime | None = Field(
        None, description="End time of the stage in GMT"
    )
    duration_seconds: StrictInt | None = Field(
        None, ge=0, description="Duration of the stage in seconds"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthSleepBase(BaseModel):
    """
    Base schema for health sleep with shared fields and validators.

    Attributes:
        date: Calendar date of the sleep session.
        sleep_start_time_gmt: Start time of sleep in GMT.
        sleep_end_time_gmt: End time of sleep in GMT.
        sleep_start_time_local: Start time of sleep in local time.
        sleep_end_time_local: End time of sleep in local time.
        total_sleep_seconds: Total duration of sleep in seconds.
        nap_time_seconds: Duration of naps in seconds.
        unmeasurable_sleep_seconds: Unmeasurable sleep duration.
        deep_sleep_seconds: Duration of deep sleep in seconds.
        light_sleep_seconds: Duration of light sleep in seconds.
        rem_sleep_seconds: Duration of REM sleep in seconds.
        awake_sleep_seconds: Duration of awake time in seconds.
        avg_heart_rate: Average heart rate during sleep.
        min_heart_rate: Minimum heart rate during sleep.
        max_heart_rate: Maximum heart rate during sleep.
        avg_spo2: Average SpO2 oxygen saturation percentage.
        lowest_spo2: Lowest SpO2 reading during sleep.
        highest_spo2: Highest SpO2 reading during sleep.
        avg_respiration: Average respiration rate.
        lowest_respiration: Lowest respiration rate.
        highest_respiration: Highest respiration rate.
        avg_stress_level: Average stress level during sleep.
        awake_count: Number of times awakened during sleep.
        restless_moments_count: Count of restless moments.
        sleep_score_overall: Overall sleep score (0-100).
        sleep_score_duration: Sleep duration score label.
        sleep_score_quality: Sleep quality score label.
        garminconnect_sleep_id: External Garmin Connect sleep ID.
        sleep_stages: List of sleep stage intervals.
        source: Data source of the sleep session.
        hrv_status: Heart rate variability status.
        resting_heart_rate: Resting heart rate during sleep.
        avg_skin_temp_deviation: Skin temp deviation in Celsius.
        awake_count_score: Awake count score label.
        rem_percentage_score: REM percentage score label.
        deep_percentage_score: Deep sleep percentage score label.
        light_percentage_score: Light sleep percentage score label.
        avg_sleep_stress: Average sleep stress level.
        sleep_stress_score: Sleep stress score label.
    """

    date: datetime_date | None = Field(
        None, description="Calendar date of the sleep session"
    )
    sleep_start_time_gmt: datetime | None = Field(
        None, description="Start time of sleep in GMT"
    )
    sleep_end_time_gmt: datetime | None = Field(
        None, description="End time of sleep in GMT"
    )
    sleep_start_time_local: datetime | None = Field(
        None, description="Start time of sleep in local time"
    )
    sleep_end_time_local: datetime | None = Field(
        None, description="End time of sleep in local time"
    )
    total_sleep_seconds: StrictInt | None = Field(
        None, ge=0, description="Total duration of sleep in seconds"
    )
    nap_time_seconds: StrictInt | None = Field(
        None, ge=0, description="Duration of naps in seconds"
    )
    unmeasurable_sleep_seconds: StrictInt | None = Field(
        None, ge=0, description="Unmeasurable sleep duration in seconds"
    )
    deep_sleep_seconds: StrictInt | None = Field(
        None, ge=0, description="Duration of deep sleep in seconds"
    )
    light_sleep_seconds: StrictInt | None = Field(
        None, ge=0, description="Duration of light sleep in seconds"
    )
    rem_sleep_seconds: StrictInt | None = Field(
        None, ge=0, description="Duration of REM sleep in seconds"
    )
    awake_sleep_seconds: StrictInt | None = Field(
        None, ge=0, description="Duration of awake time in seconds"
    )
    avg_heart_rate: StrictInt | None = Field(
        None, ge=20, le=220, description="Average heart rate during sleep"
    )
    min_heart_rate: StrictInt | None = Field(
        None, ge=20, le=220, description="Minimum heart rate during sleep"
    )
    max_heart_rate: StrictInt | None = Field(
        None, ge=20, le=220, description="Maximum heart rate during sleep"
    )
    avg_spo2: StrictInt | None = Field(
        None, ge=70, le=100, description="Average SpO2 oxygen saturation percentage"
    )
    lowest_spo2: StrictInt | None = Field(
        None, ge=70, le=100, description="Lowest SpO2 reading during sleep"
    )
    highest_spo2: StrictInt | None = Field(
        None, ge=70, le=100, description="Highest SpO2 reading during sleep"
    )
    avg_respiration: StrictInt | None = Field(
        None, ge=0, description="Average respiration rate"
    )
    lowest_respiration: StrictInt | None = Field(
        None, ge=0, description="Lowest respiration rate"
    )
    highest_respiration: StrictInt | None = Field(
        None, ge=0, description="Highest respiration rate"
    )
    avg_stress_level: StrictInt | None = Field(
        None, ge=0, le=100, description="Average stress level"
    )
    awake_count: StrictInt | None = Field(
        None, ge=0, description="Number of times awake during sleep"
    )
    restless_moments_count: StrictInt | None = Field(
        None, ge=0, description="Number of restless moments during sleep"
    )
    sleep_score_overall: StrictInt | None = Field(
        None, ge=0, le=100, description="Overall sleep score (0-100)"
    )
    sleep_score_duration: SleepScore | None = Field(
        None, description="Sleep duration score"
    )
    sleep_score_quality: SleepScore | None = Field(
        None, description="Sleep quality score"
    )
    garminconnect_sleep_id: StrictStr | None = Field(
        None, min_length=1, description="Garmin Connect sleep record ID"
    )
    sleep_stages: list[HealthSleepStage] | None = Field(
        None, description="List of sleep stages"
    )
    source: Source | None = Field(None, description="Source of the sleep data")
    hrv_status: HRVStatus | None = Field(
        None, description="Heart rate variability status"
    )
    resting_heart_rate: StrictInt | None = Field(
        None, ge=20, le=220, description="Resting heart rate"
    )
    avg_skin_temp_deviation: Decimal | None = Field(
        None, description="Average skin temperature deviation"
    )
    awake_count_score: SleepScore | None = Field(None, description="Awake count score")
    rem_percentage_score: SleepScore | None = Field(
        None, description="REM percentage score"
    )
    deep_percentage_score: SleepScore | None = Field(
        None, description="Deep sleep percentage score"
    )
    light_percentage_score: SleepScore | None = Field(
        None, description="Light sleep percentage score"
    )
    avg_sleep_stress: StrictInt | None = Field(
        None, ge=0, le=100, description="Average sleep stress"
    )
    sleep_stress_score: SleepScore | None = Field(
        None, description="Sleep stress score"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )

    @model_validator(mode="after")
    def validate_sleep_times(self) -> "HealthSleepBase":
        """Validate sleep start < end."""
        # Validate sleep start < sleep end (GMT)
        if (
            self.sleep_start_time_gmt is not None
            and self.sleep_end_time_gmt is not None
        ):
            if self.sleep_start_time_gmt >= self.sleep_end_time_gmt:
                raise ValueError("Sleep start time must be before sleep end time")

        # Validate sleep start < sleep end (Local)
        if (
            self.sleep_start_time_local is not None
            and self.sleep_end_time_local is not None
        ):
            if self.sleep_start_time_local >= self.sleep_end_time_local:
                raise ValueError(
                    "Sleep start time (local) must be before sleep end time (local)"
                )

        return self


class HealthSleepCreate(HealthSleepBase):
    """
    Schema for creating health sleep records.

    Inherits all validation from HealthSleepBase.
    Date defaults to current date if not provided.
    """

    @model_validator(mode="after")
    def set_default_date(self) -> "HealthSleepCreate":
        """Set date to today if not provided."""
        if self.date is None:
            self.date = datetime_date.today()
        return self


class HealthSleepUpdate(HealthSleepBase):
    """
    Schema for updating health sleep records.

    Inherits all validation from HealthSleepBase.
    All fields are optional for partial updates.
    ID is required to identify the record to update.
    """

    id: StrictInt = Field(
        ..., description="Unique identifier for the sleep record to update"
    )


class HealthSleepRead(HealthSleepBase):
    """
    Schema for reading health sleep records.

    Attributes:
        id: Unique identifier for the sleep record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(..., description="Unique identifier for the sleep record")
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")


class HealthSleepListResponse(BaseModel):
    """
    Response schema for health sleep list with pagination.

    Attributes:
        total: Total number of sleep records for the user.
        num_records: Number of records in this response.
        page_number: Current page number.
        records: List of health sleep records.
    """

    total: StrictInt = Field(
        ..., description="Total number of sleep records for the user"
    )
    num_records: StrictInt | None = Field(
        None, description="Number of records in this response"
    )
    page_number: StrictInt | None = Field(None, description="Current page number")
    records: list[HealthSleepRead] = Field(
        ..., description="List of health sleep records"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
