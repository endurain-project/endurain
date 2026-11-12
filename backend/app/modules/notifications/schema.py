"""Pydantic schemas for notification entities."""

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    TypeAdapter,
    field_validator,
)

import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.notifications.constants as notifications_constants

#: The most notifications one request may mark as read.
MAX_MARK_READ_IDS: Final = 100


class NotificationBase(BaseModel):
    """Base schema for notification data.

    Attributes:
        options: Additional metadata for the notification.
    """

    options: dict[str, Any] | None = Field(
        default=None,
        description="Additional notification metadata",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class NotificationCreate(NotificationBase):
    """Schema for creating a notification record.

    Attributes:
        type: Type of the notification.
        user_id: FK to user.
        source_event_id: Durable event ID for idempotent creation.
    """

    type: notifications_constants.NotificationType = Field(
        ...,
        description="Type of the notification",
    )
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


class NotificationOptions(BaseModel):
    """Base of the options a notification type stores.

    Unknown keys are ignored on read, so a row written by an older release still loads.
    """

    model_config = ConfigDict(extra="ignore")


class NoNotificationOptions(NotificationOptions):
    """The options of a notification that carries none."""


class ActivityNotificationOptions(NotificationOptions):
    """Options of a new or duplicate activity notification.

    Attributes:
        activity_id: The stored activity.
    """

    activity_id: StrictInt = Field(..., description="ID of the activity the notification is about")


class UserReferenceNotificationOptions(NotificationOptions):
    """Options of a notification that names another user.

    Attributes:
        user_id: The user the notification names.
        user_name: That user's name when the notification was created.
        user_username: That user's username when the notification was created.
    """

    user_id: StrictInt = Field(..., description="ID of the user the notification names")
    user_name: StrictStr = Field(..., description="Name of that user when the notification was created")
    user_username: StrictStr = Field(..., description="Username of that user when the notification was created")


class StravaTokenExpiredNotificationOptions(NotificationOptions):
    """Options of the notification that a Strava account was unlinked.

    Attributes:
        delete_on: The day the Strava data is deleted when Strava access was revoked; absent when the token was
            only rejected.
    """

    delete_on: date | None = Field(default=None, description="Day the user's Strava data is deleted")


class IdpLinkedNotificationOptions(NotificationOptions):
    """Options of the notification that a sign-in provider was linked.

    Attributes:
        idp_id: The linked identity provider.
        idp_name: Its name, or None when it was deleted since.
    """

    idp_id: StrictInt = Field(..., description="ID of the linked identity provider")
    idp_name: StrictStr | None = Field(default=None, description="Name of the provider, when it still exists")


class AccountSecurityChangedNotificationOptions(NotificationOptions):
    """Options of the notification that a security setting of the account changed.

    Attributes:
        change: The kind of change.
        idp_id: The identity provider concerned, for an unlink.
        idp_name: Its name, or None when it was deleted since.
        access_type: The access type the account now has, for a role change.
        backup_codes_remaining: How many unused backup codes are left, for a backup code that was used.
    """

    change: StrictStr = Field(..., description="Kind of security change")
    idp_id: StrictInt | None = Field(default=None, description="ID of the identity provider concerned")
    idp_name: StrictStr | None = Field(default=None, description="Name of the provider, when it still exists")
    access_type: StrictStr | None = Field(default=None, description="Access type the account now has")
    backup_codes_remaining: StrictInt | None = Field(default=None, description="Unused backup codes left")


class NewDeviceSignInNotificationOptions(NotificationOptions):
    """Options of the notification that the account was signed in to from a new device.

    Attributes:
        browser: The browser family of the sign-in.
        operating_system: The operating-system family of the sign-in.
        ip_address: The client address of the sign-in.
    """

    browser: StrictStr = Field(..., description="Browser family of the sign-in")
    operating_system: StrictStr = Field(..., description="Operating-system family of the sign-in")
    ip_address: StrictStr = Field(..., description="Client address of the sign-in")


class _NotificationReadBase(BaseModel):
    """What every stored notification carries.

    Attributes:
        id: Unique notification identifier.
        user_id: FK to user.
        read: Whether the notification has been read.
        created_at: Timestamp of creation.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID = Field(..., description="Unique notification ID")
    user_id: StrictInt = Field(
        ...,
        ge=1,
        description="FK to user",
    )
    read: StrictBool = Field(
        default=False,
        description="Whether notification is read",
    )
    created_at: datetime = Field(..., description="Timestamp of creation")

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        """Normalize created_at to a UTC-aware datetime.

        JSON output is then a full ISO 8601 timestamp with a UTC
        offset, which the frontend needs to compute relative times.

        Args:
            value: The datetime value to normalize.

        Returns:
            UTC-aware datetime.
        """
        return core_timezone.to_utc_aware(value)


_Type = notifications_constants.NotificationType


class ActivityNotificationRead(_NotificationReadBase):
    """A new-activity or duplicate-activity notification."""

    type: Literal[_Type.NEW_ACTIVITY, _Type.DUPLICATE_ACTIVITY] = Field(..., description="Type of the notification")
    options: ActivityNotificationOptions


class UserReferenceNotificationRead(_NotificationReadBase):
    """A follow-request, follow-accepted, sign-up-approval or admin-promoted notification, which names a user."""

    type: Literal[
        _Type.NEW_FOLLOWER_REQUEST,
        _Type.NEW_FOLLOWER_REQUEST_ACCEPTED,
        _Type.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST,
        _Type.ADMIN_USER_PROMOTED,
    ] = Field(..., description="Type of the notification")
    options: UserReferenceNotificationOptions


class AccountNoticeNotificationRead(_NotificationReadBase):
    """A Garmin-unlinked or Strava-data-deleted notification, which carries no options."""

    type: Literal[_Type.GARMIN_TOKEN_EXPIRED, _Type.STRAVA_DATA_DELETED] = Field(
        ..., description="Type of the notification"
    )
    options: NoNotificationOptions


class StravaTokenExpiredNotificationRead(_NotificationReadBase):
    """A Strava-unlinked notification."""

    type: Literal[_Type.STRAVA_TOKEN_EXPIRED] = Field(..., description="Type of the notification")
    options: StravaTokenExpiredNotificationOptions


class IdpLinkedNotificationRead(_NotificationReadBase):
    """A sign-in-provider-linked notification."""

    type: Literal[_Type.IDP_LINKED] = Field(..., description="Type of the notification")
    options: IdpLinkedNotificationOptions


class AccountSecurityChangedNotificationRead(_NotificationReadBase):
    """A security-setting-changed notification."""

    type: Literal[_Type.ACCOUNT_SECURITY_CHANGED] = Field(..., description="Type of the notification")
    options: AccountSecurityChangedNotificationOptions


class NewDeviceSignInNotificationRead(_NotificationReadBase):
    """A new-device-sign-in notification."""

    type: Literal[_Type.NEW_DEVICE_SIGN_IN] = Field(..., description="Type of the notification")
    options: NewDeviceSignInNotificationOptions


#: A stored notification. ``type`` decides which options it carries.
NotificationRead = Annotated[
    ActivityNotificationRead
    | UserReferenceNotificationRead
    | AccountNoticeNotificationRead
    | StravaTokenExpiredNotificationRead
    | IdpLinkedNotificationRead
    | AccountSecurityChangedNotificationRead
    | NewDeviceSignInNotificationRead,
    Field(discriminator="type"),
]


class NotificationPage(core_pagination.CursorPage[NotificationRead]):
    """One keyset slice of the caller's notifications.

    The list takes inserts at the head, so offset paging would repeat and skip rows across requests.
    """


NOTIFICATION_READ_ADAPTER: TypeAdapter[NotificationRead] = TypeAdapter(NotificationRead)


class NotificationUnreadCount(BaseModel):
    """The number of notifications a user has not read.

    Attributes:
        count: Number of unread notifications.
    """

    model_config = ConfigDict(extra="forbid")

    count: StrictInt = Field(..., ge=0, description="Number of unread notifications")


class NotificationsMarkRead(BaseModel):
    """The notifications to mark as read.

    Attributes:
        ids: The notifications to mark; each must be one of the caller's.
    """

    model_config = ConfigDict(extra="forbid")

    ids: list[uuid.UUID] = Field(
        ..., min_length=1, max_length=MAX_MARK_READ_IDS, description="IDs of the notifications to mark as read"
    )
