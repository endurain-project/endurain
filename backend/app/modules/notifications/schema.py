"""Pydantic schemas for notification entities."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
)

import core.timezone as core_timezone


class NotificationBase(BaseModel):
    """
    Base schema for notification data.

    Attributes:
        type: Type of the notification.
        options: Additional metadata for the notification.
    """

    type: StrictInt | None = Field(
        default=None,
        description="Type of the notification",
    )
    options: dict | None = Field(
        default=None,
        description="Additional notification metadata",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class NotificationCreate(NotificationBase):
    """
    Schema for creating a notification record.

    Attributes:
        user_id: FK to user.
    """

    user_id: StrictInt = Field(
        ...,
        ge=1,
        description="FK to user",
    )
    source_event_id: str | None = Field(
        default=None,
        max_length=36,
        description="Durable event ID for idempotent creation",
    )


class NotificationRead(NotificationBase):
    """
    Schema for reading a notification record.

    Attributes:
        id: Unique notification identifier.
        user_id: FK to user.
        read: Whether the notification has been read.
        created_at: Timestamp of creation.
    """

    id: StrictInt = Field(..., description="Unique notification ID")
    user_id: StrictInt = Field(
        ...,
        ge=1,
        description="FK to user",
    )
    read: StrictBool = Field(
        default=False,
        description="Whether notification is read",
    )
    created_at: datetime | None = Field(
        default=None,
        description="Timestamp of creation",
    )

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime | None) -> datetime | None:
        """
        Normalize created_at to a UTC-aware datetime.

        JSON output is then a full ISO 8601 timestamp with a UTC
        offset, which the frontend needs to compute relative times.

        Args:
            value: The datetime value to normalize.

        Returns:
            UTC-aware datetime or None.
        """
        return core_timezone.to_utc_aware(value)
