"""Pydantic schemas for notification entities."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_serializer,
)


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

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime | None) -> str | None:
        """
        Serialize created_at as date string.

        Args:
            value: The datetime value to serialize.

        Returns:
            Date string in YYYY-MM-DD format or None.
        """
        if value is None:
            return None
        return value.strftime("%Y-%m-%d")
