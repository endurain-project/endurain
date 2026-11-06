"""Pydantic request and response shapes for health sleep records."""

from collections.abc import Sequence
from datetime import date as datetime_date
from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_serializer,
    model_validator,
)

import core.partial_update as core_partial_update
import core.timezone as core_timezone
import core.types as core_types
from core.stored_enum import StoredStrEnum

_DATETIME = TypeAdapter(datetime)


class Source(Enum):
    """Enum representing the source of sleep health data.

    Attributes:
        GARMIN: Sleep data sourced from Garmin devices or services.
    """

    GARMIN = "garmin"


class SleepStageType(StoredStrEnum):
    """The stages of a sleep session; ``stored`` is the Garmin activity level kept in the sleep stages.

    Attributes:
        DEEP: Deep sleep, characterized by slow brain waves and muscle relaxation.
        LIGHT: Light sleep, the transition between wakefulness and deep sleep.
        REM: Rapid Eye Movement sleep, associated with vivid dreams and mental activity.
        AWAKE: Awake, the stage when the person is conscious and not sleeping.
    """

    DEEP = ("deep", 0)
    LIGHT = ("light", 1)
    REM = ("rem", 2)
    AWAKE = ("awake", 3)


#: The stage type of a stored row, a provider sync or an archive written before the types were strings, which
#: hand over the stored number. A client writes the plain enum, which refuses the number.
StoredSleepStageType = Annotated[SleepStageType, BeforeValidator(SleepStageType.accept_stored)]


class HRVStatus(Enum):
    """Enum representing the Heart Rate Variability (HRV) status classification.

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
    """Enumeration of sleep quality score levels.

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
    """Represents a sleep stage with timing and duration information.

    This model captures details about individual sleep stages within a sleep session,
    including the type of stage, when it occurred, and how long it lasted.

    Attributes:
        stage_type: The classification of the sleep stage (e.g., light, deep, REM).
        start_time_gmt: The beginning timestamp of the sleep stage in GMT timezone.
        end_time_gmt: The ending timestamp of the sleep stage in GMT timezone.
        duration_seconds: The length of the sleep stage in seconds. Must be non-negative.
    """

    stage_type: StoredSleepStageType | None = Field(default=None, description="Type of sleep stage")
    start_time_gmt: datetime | None = Field(default=None, description="Start time of the stage in GMT")
    end_time_gmt: datetime | None = Field(default=None, description="End time of the stage in GMT")
    duration_seconds: StrictInt | None = Field(default=None, ge=0, description="Duration of the stage in seconds")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    @field_serializer("start_time_gmt", "end_time_gmt")
    def serialize_time(self, value: datetime | None) -> str | None:
        """Dump a stage time as ISO 8601 text in every mode, as the JSON column that stores the stages requires.

        Args:
            value: The time, or ``None``.

        Returns:
            The time as the API writes it in JSON, or ``None``.
        """
        return None if value is None else _DATETIME.dump_python(value, mode="json")


class HealthSleepBase(BaseModel):
    """Pydantic model representing the base schema for health sleep data.

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
        sleep_stages (list[SleepStage] | None): List of sleep stages.
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

    date: datetime_date | None = Field(default=None, description="Calendar date of the sleep session")
    sleep_start_time_gmt: datetime | None = Field(default=None, description="Start time of sleep in GMT")
    sleep_end_time_gmt: datetime | None = Field(default=None, description="End time of sleep in GMT")
    sleep_start_time_local: datetime | None = Field(default=None, description="Start time of sleep in local time")
    sleep_end_time_local: datetime | None = Field(default=None, description="End time of sleep in local time")
    total_sleep_seconds: StrictInt | None = Field(default=None, ge=0, description="Total duration of sleep in seconds")
    nap_time_seconds: StrictInt | None = Field(default=None, ge=0, description="Duration of naps in seconds")
    unmeasurable_sleep_seconds: StrictInt | None = Field(
        default=None, ge=0, description="Unmeasurable sleep duration in seconds"
    )
    deep_sleep_seconds: StrictInt | None = Field(default=None, ge=0, description="Duration of deep sleep in seconds")
    light_sleep_seconds: StrictInt | None = Field(default=None, ge=0, description="Duration of light sleep in seconds")
    rem_sleep_seconds: StrictInt | None = Field(default=None, ge=0, description="Duration of REM sleep in seconds")
    awake_sleep_seconds: StrictInt | None = Field(default=None, ge=0, description="Duration of awake time in seconds")
    avg_heart_rate: StrictInt | None = Field(default=None, ge=20, le=220, description="Average heart rate during sleep")
    min_heart_rate: StrictInt | None = Field(default=None, ge=20, le=220, description="Minimum heart rate during sleep")
    max_heart_rate: StrictInt | None = Field(default=None, ge=20, le=220, description="Maximum heart rate during sleep")
    avg_spo2: StrictInt | None = Field(
        default=None,
        ge=70,
        le=100,
        description="Average SpO2 oxygen saturation percentage",
    )
    lowest_spo2: StrictInt | None = Field(default=None, ge=70, le=100, description="Lowest SpO2 reading during sleep")
    highest_spo2: StrictInt | None = Field(default=None, ge=70, le=100, description="Highest SpO2 reading during sleep")
    avg_respiration: StrictInt | None = Field(default=None, ge=0, description="Average respiration rate")
    lowest_respiration: StrictInt | None = Field(default=None, ge=0, description="Lowest respiration rate")
    highest_respiration: StrictInt | None = Field(default=None, ge=0, description="Highest respiration rate")
    avg_stress_level: StrictInt | None = Field(default=None, ge=0, le=100, description="Average stress level")
    awake_count: StrictInt | None = Field(default=None, ge=0, description="Number of times awake during sleep")
    restless_moments_count: StrictInt | None = Field(
        default=None, ge=0, description="Number of restless moments during sleep"
    )
    sleep_score_overall: StrictInt | None = Field(default=None, ge=0, le=100, description="Overall sleep score (0-100)")
    sleep_score_duration: SleepScore | None = Field(default=None, description="Sleep duration score")
    sleep_score_quality: SleepScore | None = Field(default=None, description="Sleep quality score")
    sleep_stages: Sequence[HealthSleepStage] | None = Field(default=None, description="List of sleep stages")
    hrv_status: HRVStatus | None = Field(default=None, description="Heart rate variability status")
    resting_heart_rate: StrictInt | None = Field(default=None, ge=20, le=220, description="Resting heart rate")
    avg_skin_temp_deviation: StrictFloat | None = Field(default=None, description="Average skin temperature deviation")
    awake_count_score: SleepScore | None = Field(default=None, description="Awake count score")
    rem_percentage_score: SleepScore | None = Field(default=None, description="REM percentage score")
    deep_percentage_score: SleepScore | None = Field(default=None, description="Deep sleep percentage score")
    light_percentage_score: SleepScore | None = Field(default=None, description="Light sleep percentage score")
    avg_sleep_stress: StrictInt | None = Field(default=None, ge=0, le=100, description="Average sleep stress")
    sleep_stress_score: SleepScore | None = Field(default=None, description="Sleep stress score")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )

    @model_validator(mode="after")
    def validate_sleep_times(self) -> "HealthSleepBase":
        """Validate sleep start < end, reading a time without an offset as UTC."""
        if (
            self.sleep_start_time_gmt is not None
            and self.sleep_end_time_gmt is not None
            and core_timezone.to_utc_aware(self.sleep_start_time_gmt)
            >= core_timezone.to_utc_aware(self.sleep_end_time_gmt)
        ):
            raise ValueError("Sleep start time must be before sleep end time")

        if (
            self.sleep_start_time_local is not None
            and self.sleep_end_time_local is not None
            and core_timezone.to_utc_aware(self.sleep_start_time_local)
            >= core_timezone.to_utc_aware(self.sleep_end_time_local)
        ):
            raise ValueError("Sleep start time (local) must be before sleep end time (local)")

        return self


class HealthSleepStageWrite(HealthSleepStage):
    """A sleep stage a client writes: its times are bounded, which a stored stage read back need not be."""

    stage_type: SleepStageType | None = Field(default=None, description="Type of sleep stage")
    start_time_gmt: core_types.RecordDateTime | None = Field(default=None, description="Start time of the stage in GMT")
    end_time_gmt: core_types.RecordDateTime | None = Field(default=None, description="End time of the stage in GMT")


class HealthSleepStageImport(HealthSleepStageWrite):
    """A sleep stage the server writes: a provider sync or a profile import, which may hand over the stored number."""

    stage_type: StoredSleepStageType | None = Field(default=None, description="Type of sleep stage")


class HealthSleepWrite(HealthSleepBase):
    """Sleep fields a client writes: the date and times are bounded, which a stored row read back need not be."""

    date: core_types.RecordDate | None = Field(default=None, description="Calendar date of the sleep session")
    sleep_start_time_gmt: core_types.RecordDateTime | None = Field(
        default=None, description="Start time of sleep in GMT"
    )
    sleep_end_time_gmt: core_types.RecordDateTime | None = Field(default=None, description="End time of sleep in GMT")
    sleep_start_time_local: core_types.RecordDateTime | None = Field(
        default=None, description="Start time of sleep in local time"
    )
    sleep_end_time_local: core_types.RecordDateTime | None = Field(
        default=None, description="End time of sleep in local time"
    )
    sleep_stages: Sequence[HealthSleepStageWrite] | None = Field(default=None, description="List of sleep stages")


class HealthSleepCreate(HealthSleepWrite):
    """Schema for creating a health sleep record.

    The date is optional; ``service`` fills it in when the client sends none.
    """


class HealthSleepRead(HealthSleepBase):
    """Read schema for health sleep records.

    Extends the base health sleep schema with an identifier field for retrieving
    or referencing existing sleep records in the database.

    Attributes:
        garminconnect_sleep_id (StrictStr | None): Garmin Connect sleep record ID.
        source (Source | None): Source of the sleep data.
        user_id (StrictInt): Foreign key reference to the user.
        id (StrictInt): Unique identifier for the sleep record to update or retrieve.
    """

    garminconnect_sleep_id: StrictStr | None = Field(
        default=None, min_length=1, description="Garmin Connect sleep record ID"
    )
    source: Source | None = Field(default=None, description="Source of the sleep data")
    id: StrictInt = Field(..., description="Unique identifier for the sleep record to update")
    user_id: StrictInt = Field(..., description="Foreign key reference to the user")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")


class HealthSleepUpdate(core_partial_update.NotClearable, HealthSleepWrite):
    """Schema for the fields a PATCH changes on a sleep record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    not_clearable = ("date",)


class HealthSleepImport(HealthSleepCreate):
    """Sleep record written by the server itself: a provider sync or a profile import.

    Unlike :class:`HealthSleepCreate` it carries the provenance, which a client never sets. Every
    server-side writer of ``source`` takes ``Health<Kind>Import`` (create) or ``Health<Kind>ImportUpdate``.

    Attributes:
        garminconnect_sleep_id (StrictStr | None): Garmin Connect sleep record ID.
        source (Source | None): The source the record came from.
    """

    garminconnect_sleep_id: StrictStr | None = Field(
        default=None, min_length=1, description="Garmin Connect sleep record ID"
    )
    source: Source | None = Field(default=None, description="Source of the sleep data")
    sleep_stages: Sequence[HealthSleepStageImport] | None = Field(default=None, description="List of sleep stages")


class HealthSleepImportUpdate(HealthSleepUpdate):
    """Fields a provider sync or a profile import changes on a sleep record, provenance included.

    Attributes:
        garminconnect_sleep_id (StrictStr | None): Garmin Connect sleep record ID.
        source (Source | None): The source the record came from.
    """

    garminconnect_sleep_id: StrictStr | None = Field(
        default=None, min_length=1, description="Garmin Connect sleep record ID"
    )
    source: Source | None = Field(default=None, description="Source of the sleep data")
    sleep_stages: Sequence[HealthSleepStageImport] | None = Field(default=None, description="List of sleep stages")
