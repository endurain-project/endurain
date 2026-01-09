from enum import Enum
from pydantic import (
    BaseModel,
    ConfigDict,
    model_validator,
    StrictInt,
    StrictStr,
    StrictFloat,
    Field,
)
from datetime import datetime, date as datetime_date


class Source(Enum):
    """
    Enum representing the source of sleep health data.

    Attributes:
        GARMIN: Sleep data sourced from Garmin devices or services.
    """

    GARMIN = "garmin"


class SleepStageType(Enum):
    """
    Enum representing different stages of sleep.

    Attributes:
        DEEP (int): Deep sleep stage, value 0. Characterized by slow brain waves and muscle relaxation.
        LIGHT (int): Light sleep stage, value 1. Transitional sleep between wakefulness and deep sleep.
        REM (int): Rapid Eye Movement sleep stage, value 2. Associated with vivid dreams and mental activity.
        AWAKE (int): Awake state, value 3. The stage when the person is conscious and not sleeping.
    """

    DEEP = 0
    LIGHT = 1
    REM = 2
    AWAKE = 3


class HRVStatus(Enum):
    """
    Enum representing the Heart Rate Variability (HRV) status classification.

    Attributes:
        BALANCED: Indicates healthy HRV levels with good cardiovascular autonomic balance.
        UNBALANCED: Indicates HRV levels showing some autonomic imbalance or stress.
        LOW: Indicates HRV levels that are lower than optimal, suggesting fatigue or overtraining.
        POOR: Indicates critically low HRV levels, suggesting significant stress, illness, or recovery issues.
    """

    BALANCED = "BALANCED"
    UNBALANCED = "UNBALANCED"
    LOW = "LOW"
    POOR = "POOR"


class SleepScore(Enum):
    """
    Enumeration of sleep quality score levels.

    Attributes:
        EXCELLENT (str): Represents excellent sleep quality.
        GOOD (str): Represents good sleep quality.
        FAIR (str): Represents fair sleep quality.
        POOR (str): Represents poor sleep quality.
    """

    EXCELLENT = "EXCELLENT"
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"


class HealthSleepStage(BaseModel):
    """
    Represents a sleep stage with timing and duration information.

    This model captures details about individual sleep stages within a sleep session,
    including the type of stage, when it occurred, and how long it lasted.

    Attributes:
        stage_type: The classification of the sleep stage (e.g., light, deep, REM).
        start_time_gmt: The beginning timestamp of the sleep stage in GMT timezone.
        end_time_gmt: The ending timestamp of the sleep stage in GMT timezone.
        duration_seconds: The length of the sleep stage in seconds. Must be non-negative.
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
    Pydantic model representing the base schema for health sleep data.

    This model defines the structure and validation rules for sleep-related health metrics,
    including sleep duration, quality scores, heart rate variability, oxygen saturation,
    respiration rates, and sleep stages.

    Attributes:
        date (datetime_date | None): Calendar date of the sleep session.
        sleep_start_time_gmt (datetime | None): Start time of sleep in GMT.
        sleep_end_time_gmt (datetime | None): End time of sleep in GMT.
        sleep_start_time_local (datetime | None): Start time of sleep in local time.
        sleep_end_time_local (datetime | None): End time of sleep in local time.
        total_sleep_seconds (StrictInt | None): Total duration of sleep in seconds (>= 0).
        nap_time_seconds (StrictInt | None): Duration of naps in seconds (>= 0).
        unmeasurable_sleep_seconds (StrictInt | None): Unmeasurable sleep duration in seconds (>= 0).
        deep_sleep_seconds (StrictInt | None): Duration of deep sleep in seconds (>= 0).
        light_sleep_seconds (StrictInt | None): Duration of light sleep in seconds (>= 0).
        rem_sleep_seconds (StrictInt | None): Duration of REM sleep in seconds (>= 0).
        awake_sleep_seconds (StrictInt | None): Duration of awake time in seconds (>= 0).
        avg_heart_rate (StrictInt | None): Average heart rate during sleep (20-220 bpm).
        min_heart_rate (StrictInt | None): Minimum heart rate during sleep (20-220 bpm).
        max_heart_rate (StrictInt | None): Maximum heart rate during sleep (20-220 bpm).
        avg_spo2 (StrictInt | None): Average SpO2 oxygen saturation percentage (70-100%).
        lowest_spo2 (StrictInt | None): Lowest SpO2 reading during sleep (70-100%).
        highest_spo2 (StrictInt | None): Highest SpO2 reading during sleep (70-100%).
        avg_respiration (StrictInt | None): Average respiration rate (>= 0).
        lowest_respiration (StrictInt | None): Lowest respiration rate (>= 0).
        highest_respiration (StrictInt | None): Highest respiration rate (>= 0).
        avg_stress_level (StrictInt | None): Average stress level (0-100).
        awake_count (StrictInt | None): Number of times awake during sleep (>= 0).
        restless_moments_count (StrictInt | None): Number of restless moments during sleep (>= 0).
        sleep_score_overall (StrictInt | None): Overall sleep score (0-100).
        sleep_score_duration (SleepScore | None): Sleep duration score.
        sleep_score_quality (SleepScore | None): Sleep quality score.
        garminconnect_sleep_id (StrictStr | None): Garmin Connect sleep record ID.
        sleep_stages (list[SleepStage] | None): List of sleep stages.
        source (Source | None): Source of the sleep data.
        hrv_status (HRVStatus | None): Heart rate variability status.
        resting_heart_rate (StrictInt | None): Resting heart rate (20-220 bpm).
        avg_skin_temp_deviation (StrictFloat | None): Average skin temperature deviation.
        awake_count_score (SleepScore | None): Awake count score.
        rem_percentage_score (SleepScore | None): REM percentage score.
        deep_percentage_score (SleepScore | None): Deep sleep percentage score.
        light_percentage_score (SleepScore | None): Light sleep percentage score.
        avg_sleep_stress (StrictInt | None): Average sleep stress (0-100).
        sleep_stress_score (SleepScore | None): Sleep stress score.

    Model Configuration:
        - Allows population from ORM attributes
        - Forbids extra fields
        - Validates on assignment
        - Uses enum values in serialization

    Validators:
        validate_sleep_times: Ensures sleep start time is before sleep end time
                             for both GMT and local time zones.
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
    avg_skin_temp_deviation: StrictFloat | None = Field(
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
    Validator for HealthSleepCreate model that automatically sets the date field.

    This validator runs after model initialization to ensure that if no date
    is provided, it defaults to today's date.

    Returns:
        HealthSleepCreate: The validated model instance with date set to today if it was None.
    """

    @model_validator(mode="after")
    def set_default_date(self) -> "HealthSleepCreate":
        """Set date to today if not provided."""
        if self.date is None:
            self.date = datetime_date.today()
        return self


class HealthSleepRead(HealthSleepBase):
    """
    Read schema for health sleep records.

    Extends the base health sleep schema with an identifier field for retrieving
    or referencing existing sleep records in the database.

    Attributes:
        user_id (StrictInt): Foreign key reference to the user.
        id (StrictInt): Unique identifier for the sleep record to update or retrieve.
    """

    id: StrictInt = Field(
        ..., description="Unique identifier for the sleep record to update"
    )
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")


class HealthSleepUpdate(HealthSleepRead):
    """
    Schema for updating health sleep records.

    Inherits all fields from HealthSleepRead, allowing clients to update
    existing sleep data while maintaining consistency with the read schema.

    Used in PUT/PATCH requests to modify sleep tracking information such as
    sleep duration, quality, and related health metrics.
    """


class HealthSleepListResponse(BaseModel):
    """
    Response model for paginated health sleep records.

    This model represents the paginated response structure for retrieving a user's sleep records.
    It includes pagination metadata and a list of individual sleep record details.

    Attributes:
        total (StrictInt): Total number of sleep records available for the user.
        num_records (StrictInt | None): Number of records included in this response page.
        page_number (StrictInt | None): Current page number of the paginated results.
        records (list[HealthSleepRead]): List of health sleep record objects for the current page.
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
