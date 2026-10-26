"""Constants for notification-related modules."""

from enum import IntEnum


class NotificationType(IntEnum):
    """Enumeration of notification types.

    Attributes:
        NEW_ACTIVITY: New activity notification.
        DUPLICATE_ACTIVITY: Duplicate activity notification.
        NEW_FOLLOWER_REQUEST: New follower request notification.
        NEW_FOLLOWER_REQUEST_ACCEPTED: Follower request accepted notification.
        GARMIN_TOKEN_EXPIRED: Garmin Connect account unlinked after its token expired.
        STRAVA_TOKEN_EXPIRED: Strava account unlinked after Strava rejected its token.
        ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST: Admin sign-up approval request
            notification.
    """

    NEW_ACTIVITY = 1
    DUPLICATE_ACTIVITY = 2
    NEW_FOLLOWER_REQUEST = 11
    NEW_FOLLOWER_REQUEST_ACCEPTED = 12
    GARMIN_TOKEN_EXPIRED = 21
    STRAVA_TOKEN_EXPIRED = 22
    ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST = 101


# Websocket message types pushed to the browser alongside a stored notification.
NEW_ACTIVITY_WS_MESSAGE = "NEW_ACTIVITY_NOTIFICATION"
DUPLICATE_ACTIVITY_WS_MESSAGE = "NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION"
NEW_FOLLOWER_REQUEST_WS_MESSAGE = "NEW_FOLLOWER_REQUEST_NOTIFICATION"
NEW_FOLLOWER_REQUEST_REMOVED_WS_MESSAGE = "NEW_FOLLOWER_REQUEST_REMOVED_NOTIFICATION"
NEW_FOLLOWER_REQUEST_ACCEPTED_WS_MESSAGE = "NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION"
GARMIN_UNLINKED_WS_MESSAGE = "GARMIN_TOKEN_EXPIRED_NOTIFICATION"
STRAVA_UNLINKED_WS_MESSAGE = "STRAVA_TOKEN_EXPIRED_NOTIFICATION"
ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_WS_MESSAGE = "ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_NOTIFICATION"

# Rows deleted per transaction by the sweep, so it never holds a long lock.
PURGE_BATCH_SIZE = 1000
