"""
Pydantic schemas for health fasting data.

This module defines the request/response schemas for fasting tracking,
including validation rules and enumerations for fasting types and statuses.
"""

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)

import modules.health.schema as health_schema


class Source(Enum):
    """
    Enumeration of data sources for fasting records.

    Attributes:
        MANUAL: Manually entered fasting data.
        GARMIN: Garmin fitness tracking platform as a data source.
    """

    MANUAL = "manual"
    GARMIN = "garmin"


class FastingType(Enum):
    """
    Enumeration of fasting protocol types.

    Attributes:
        IF_16_8: 16-hour fast with 8-hour eating window.
        IF_18_6: 18-hour fast with 6-hour eating window.
        IF_20_4: 20-hour fast with 4-hour eating window.
        OMAD: One meal a day (23:1 ratio).
        EXTENDED_24: 24-hour extended fast.
        EXTENDED_36: 36-hour extended fast.
        EXTENDED_48: 48-hour extended fast.
        EXTENDED_72: 72-hour extended fast.
        CUSTOM: Custom fasting duration.
    """

    IF_16_8 = "16:8"
    IF_18_6 = "18:6"
    IF_20_4 = "20:4"
    OMAD = "OMAD"
    EXTENDED_24 = "24h"
    EXTENDED_36 = "36h"
    EXTENDED_48 = "48h"
    EXTENDED_72 = "72h"
    CUSTOM = "custom"


class FastingStatus(Enum):
    """
    Enumeration of fasting session statuses.

    Attributes:
        IN_PROGRESS: Fasting session is currently active.
        COMPLETED: Fasting session completed successfully.
        BROKEN: Fasting session was broken before target.
        CANCELLED: Fasting session was cancelled.
    """

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BROKEN = "broken"
    CANCELLED = "cancelled"


class HealthFastingBase(BaseModel):
    """
    Base schema for health fasting data.

    Attributes:
        fast_start_time: Start time of fast.
        fast_end_time: End time of fast.
        target_duration_seconds: Target fasting duration in seconds.
        actual_duration_seconds: Actual fasting duration in seconds.
        fasting_type: Type of fasting protocol.
        status: Current status of the fasting session.
        notes: Optional notes about the fasting session.
        source: Data source for the record.
    """

    fast_start_time: datetime | None = Field(
        default=None,
        description="Start time of fast",
    )
    fast_end_time: datetime | None = Field(
        default=None,
        description="End time of fast (null if ongoing)",
    )
    target_duration_seconds: StrictInt | None = Field(
        default=None,
        ge=0,
        le=259200,  # Max 72 hours
        description="Target fasting duration in seconds (max 72h)",
    )
    actual_duration_seconds: StrictInt | None = Field(
        default=None,
        ge=0,
        description="Actual fasting duration in seconds",
    )
    fasting_type: FastingType | None = Field(
        default=None,
        description="Type of fasting protocol",
    )
    status: FastingStatus | None = Field(
        default=None,
        description="Current status of the fasting session",
    )
    notes: StrictStr | None = Field(
        default=None,
        max_length=500,
        description="Optional notes about the fasting session",
    )
    source: Source | None = Field(
        default=None,
        description="Data source for the record",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthFastingCreate(HealthFastingBase):
    """
    Schema for creating a new fasting session.

    Requires start time and sets defaults for status.
    """

    @model_validator(mode="after")
    def set_defaults_and_validate(self) -> "HealthFastingCreate":
        """
        Validate required fields and set defaults.

        Returns:
            The validated model instance with defaults set.

        Raises:
            ValueError: If fast_start_time is not provided.
        """
        if self.fast_start_time is None:
            raise ValueError("fast_start_time is required")
        if self.status is None:
            self.status = FastingStatus.IN_PROGRESS
        if self.source is None:
            self.source = Source.MANUAL
        return self


class HealthFastingRead(HealthFastingBase):
    """
    Schema for reading a fasting record.

    Attributes:
        id: Unique identifier for the fasting record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier for the fasting record",
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key reference to the user",
    )


class HealthFastingUpdate(HealthFastingRead):
    """
    Schema for updating a fasting record.

    Inherits from HealthFastingRead for consistency with read operations.
    """


class HealthFastingComplete(BaseModel):
    """
    Schema for completing or ending a fasting session.

    Attributes:
        fast_end_time: End time of fast.
        status: Final status of the fasting session.
        notes: Optional notes about the fasting session.
    """

    fast_end_time: datetime = Field(
        ...,
        description="End time of fast",
    )
    status: FastingStatus = Field(
        default=FastingStatus.COMPLETED,
        description="Final status of the fasting session",
    )
    notes: StrictStr | None = Field(
        default=None,
        max_length=500,
        description="Optional notes about the fasting session",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthFastingListResponse(health_schema.HealthListResponse):
    """
    Response model for listing health fasting records.

    Extends the base HealthListResponse to provide a typed response containing
    a list of fasting records. This model is used when returning multiple
    fasting entries from API endpoints.

    Attributes:
        records: A list of HealthFastingRead objects representing individual
        fasting records.
    """

    records: list[HealthFastingRead] = Field(
        ...,
        description="List of fasting records",
    )


class HealthFastingStatsResponse(BaseModel):
    """
    Response model for fasting statistics.

    Attributes:
        total_fasts: Total number of completed fasts.
        current_streak: Current consecutive days of fasting.
        longest_streak: Longest consecutive days of fasting.
        avg_duration_seconds: Average fasting duration in seconds.
        total_fasting_seconds: Total time spent fasting.
        completion_rate: Percentage of fasts completed vs started.
    """

    total_fasts: StrictInt = Field(
        ...,
        description="Total number of completed fasts",
    )
    current_streak: StrictInt = Field(
        ...,
        description="Current consecutive days of fasting",
    )
    longest_streak: StrictInt = Field(
        ...,
        description="Longest consecutive days of fasting",
    )
    avg_duration_seconds: StrictInt | None = Field(
        default=None,
        description="Average fasting duration in seconds",
    )
    total_fasting_seconds: StrictInt = Field(
        ...,
        description="Total time spent fasting in seconds",
    )
    completion_rate: float = Field(
        ...,
        ge=0,
        le=100,
        description="Percentage of fasts completed vs started",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )
