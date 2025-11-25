from enum import Enum
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
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


class HealthSleepStage(BaseModel):
    """
    Represents individual sleep stage interval.

    Attributes:
        stage_type: Type of sleep stage.
        start_time_gmt: Start time of the stage in GMT.
        end_time_gmt: End time of the stage in GMT.
        duration_seconds: Duration of the stage in seconds.
    """

    stage_type: SleepStageType | None = None
    start_time_gmt: datetime | None = None
    end_time_gmt: datetime | None = None
    duration_seconds: int | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthSleep(BaseModel):
    """
    Represents a sleep session with detailed metrics.

    Attributes:
        id: Unique identifier for the sleep session.
        user_id: Foreign key reference to the user.
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
        sleep_score_overall: Overall sleep score.
        sleep_score_duration: Sleep duration score.
        sleep_score_quality: Sleep quality score.
        garminconnect_sleep_id: External Garmin Connect sleep ID.
        sleep_stages: List of sleep stage intervals as JSON.
        source: Data source of the sleep session.
        created_at: Timestamp when record was created.
        updated_at: Timestamp when record was last updated.
    """

    id: int | None = None
    user_id: int | None = None
    date: datetime_date | None = None
    sleep_start_time_gmt: datetime | None = None
    sleep_end_time_gmt: datetime | None = None
    sleep_start_time_local: datetime | None = None
    sleep_end_time_local: datetime | None = None
    total_sleep_seconds: int | None = None
    nap_time_seconds: int | None = None
    unmeasurable_sleep_seconds: int | None = None
    deep_sleep_seconds: int | None = None
    light_sleep_seconds: int | None = None
    rem_sleep_seconds: int | None = None
    awake_sleep_seconds: int | None = None
    avg_heart_rate: Decimal | None = None
    min_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_spo2: Decimal | None = None
    lowest_spo2: int | None = None
    highest_spo2: int | None = None
    avg_respiration: Decimal | None = None
    lowest_respiration: Decimal | None = None
    highest_respiration: Decimal | None = None
    avg_stress_level: Decimal | None = None
    awake_count: int | None = None
    restless_moments_count: int | None = None
    sleep_score_overall: int | None = None
    sleep_score_duration: str | None = None
    sleep_score_quality: str | None = None
    garminconnect_sleep_id: str | None = None
    sleep_stages: list[HealthSleepStage] | None = None
    source: Source | None = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )

    @field_validator("avg_heart_rate", "min_heart_rate", "max_heart_rate")
    @classmethod
    def validate_heart_rate(cls, v: int | Decimal | None) -> int | Decimal | None:
        """Validate heart rate is within reasonable range (20-220 bpm)."""
        if v is not None:
            value = float(v) if isinstance(v, Decimal) else v
            if value < 20 or value > 220:
                raise ValueError("Heart rate must be between 20 and 220 bpm")
        return v

    @field_validator("avg_spo2", "lowest_spo2", "highest_spo2")
    @classmethod
    def validate_spo2(cls, v: int | Decimal | None) -> int | Decimal | None:
        """Validate SpO2 is within reasonable range (70-100%)."""
        if v is not None:
            value = float(v) if isinstance(v, Decimal) else v
            if value < 70 or value > 100:
                raise ValueError("SpO2 must be between 70 and 100%")
        return v

    @model_validator(mode="after")
    def validate_sleep_times(self) -> "HealthSleep":
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
