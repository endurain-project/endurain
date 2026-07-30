"""Activity sets schemas."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_serializer,
)

import core.timezone as core_timezone


class ActivitySetsBase(BaseModel):
    """
    Base schema for activity workout sets.

    Attributes:
        duration: Set duration.
        repetitions: Repetitions count.
        weight: Exercise weight.
        set_type: Workout set type string.
        start_time: Set start time ISO string.
        category: Category identifier.
        category_subtype: Category sub type.
    """

    duration: StrictFloat
    repetitions: StrictInt | None = None
    weight: StrictFloat | None = None
    set_type: StrictStr
    start_time: StrictStr
    category: StrictInt | None = None
    category_subtype: StrictInt | None = None

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class ActivitySetsCreate(ActivitySetsBase):
    """
    Schema for creating activity workout sets.

    Attributes:
        activity_id: Parent activity ID.
    """

    activity_id: StrictInt


class ActivitySetsRead(ActivitySetsBase):
    """
    Schema for reading activity workout sets.

    Attributes:
        id: Activity set primary key.
        activity_id: Parent activity ID.
        start_time: Set start time as datetime.
        timezone: Activity timezone for
            serialization (excluded from output).
    """

    id: StrictInt
    activity_id: StrictInt
    start_time: datetime  # type: ignore[assignment]
    timezone: StrictStr | None = Field(default=None, exclude=True)

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    @field_serializer("start_time")
    def serialize_start_time(self, value: datetime) -> str:
        """
        Format start_time with activity timezone.

        Args:
            value: The datetime value to serialize.

        Returns:
            Formatted datetime string.
        """
        return core_timezone.format_aware_datetime(value, self.timezone)
