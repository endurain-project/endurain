"""Constants for notification-related modules."""

from enum import IntEnum


class NotificationType(IntEnum):
    """
    Enumeration of notification types.

    Attributes:
        NEW_ACTIVITY: New activity notification.
        DUPLICATE_ACTIVITY: Duplicate activity notification.
        NEW_FOLLOWER_REQUEST: New follower request notification.
        NEW_FOLLOWER_REQUEST_ACCEPTED: Follower request accepted notification.
        ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST: Admin sign-up approval request
            notification.
    """

    NEW_ACTIVITY = 1
    DUPLICATE_ACTIVITY = 2
    NEW_FOLLOWER_REQUEST = 11
    NEW_FOLLOWER_REQUEST_ACCEPTED = 12
    GARMIN_TOKEN_EXPIRED = 21
    ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST = 101
