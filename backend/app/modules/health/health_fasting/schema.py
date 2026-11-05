"""Pydantic schemas for health fasting data.

This module defines the request/response schemas for fasting tracking,
including validation rules and enumerations for fasting types and statuses.
"""

from datetime import datetime
from enum import Enum, StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

import core.partial_update as core_partial_update
import core.types as core_types


class Source(Enum):
    """Enumeration of data sources for fasting records.

    Attributes:
        MANUAL: Manually entered fasting data.
        GARMIN: Garmin fitness tracking platform as a data source.
    """

    MANUAL = "manual"
    GARMIN = "garmin"


class FastingType(Enum):
    """Enumeration of fasting protocol types.

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


class FastingStatus(StrEnum):
    """Enumeration of fasting session statuses.

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
    """Base schema for health fasting data.

    Attributes:
        fast_start_time: Start time of fast.
        fast_end_time: End time of fast.
        target_duration_seconds: Target fasting duration in seconds.
        fasting_type: Type of fasting protocol.
        status: Current status of the fasting session.
        notes: Optional notes about the fasting session.
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

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthFastingWrite(HealthFastingBase):
    """Fasting fields a client writes: the times are bounded, which a stored row read back need not be."""

    fast_start_time: core_types.RecordDateTime | None = Field(
        default=None,
        description="Start time of fast",
    )
    fast_end_time: core_types.RecordDateTime | None = Field(
        default=None,
        description="End time of fast (null if ongoing)",
    )


class HealthFastingCreate(HealthFastingWrite):
    """Schema for creating a new fasting session.

    Requires start time and sets defaults for status.
    """

    fast_start_time: core_types.RecordDateTime = Field(
        ...,
        description="Start time of fast",
    )

    @model_validator(mode="after")
    def set_defaults_and_validate(self) -> "HealthFastingCreate":
        """Set the defaults of the fields left out.

        Returns:
            The validated model instance with defaults set.
        """
        if self.status is None:
            self.status = FastingStatus.IN_PROGRESS
        return self


class HealthFastingRead(HealthFastingBase):
    """Schema for reading a fasting record.

    Attributes:
        source: Data source for the record.
        id: Unique identifier for the fasting record.
        user_id: Foreign key reference to the user.
        actual_duration_seconds: Seconds between the start and end time, derived by the server.
    """

    source: Source | None = Field(
        default=None,
        description="Data source for the record",
    )
    id: StrictInt = Field(
        ...,
        description="Unique identifier for the fasting record",
    )
    fast_start_time: datetime = Field(
        ...,
        description="Start time of fast",
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key reference to the user",
    )
    actual_duration_seconds: StrictInt | None = Field(
        default=None,
        ge=0,
        description="Seconds between the start and the end time, derived by the server; null while the fast has no end",
    )
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")


class HealthFastingUpdate(core_partial_update.NotClearable, HealthFastingWrite):
    """Schema for the fields a PATCH changes on a fasting record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    not_clearable = ("fast_start_time", "status")


class HealthFastingImport(HealthFastingCreate):
    """Fasting session written by the server itself: a profile import, or a client's session with its source.

    Unlike :class:`HealthFastingCreate` it carries the provenance, which a client never sets. Every
    server-side writer of ``source`` takes ``Health<Kind>Import`` (create) or ``Health<Kind>ImportUpdate``. A
    session without a source is a manual one.

    Attributes:
        source: The source the session came from; ``manual`` when none is given.
    """

    source: Source | None = Field(default=None, description="Data source for the record")

    @model_validator(mode="after")
    def set_default_source(self) -> "HealthFastingImport":
        """Make a session without a source a manual one.

        Returns:
            The validated model instance with the source set.
        """
        if self.source is None:
            self.source = Source.MANUAL
        return self


class HealthFastingComplete(BaseModel):
    """Schema for completing or ending a fasting session.

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
        validate_default=True,
        description="Final status of the fasting session",
    )
    notes: StrictStr | None = Field(
        default=None,
        max_length=500,
        description="Optional notes about the fasting session",
    )

    @field_validator("status")
    @classmethod
    def _status_ends_the_fast(cls, value: FastingStatus) -> FastingStatus:
        """Refuse ``in_progress``: completing a fast ends it.

        Args:
            value: The final status in the request.

        Returns:
            The final status.

        Raises:
            ValueError: When the status is ``in_progress``.
        """
        # ``use_enum_values`` hands the validator the plain string.
        if getattr(value, "value", value) == FastingStatus.IN_PROGRESS.value:
            raise ValueError("A completed fast cannot still be in progress")
        return value

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthFastingStatsResponse(BaseModel):
    """Response model for fasting statistics.

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
