"""Constants for notification-related modules."""

from core.stored_enum import StoredStrEnum


class NotificationType(StoredStrEnum):
    """Enumeration of notification types; ``stored`` is the integer in ``notifications.type``.

    Attributes:
        NEW_ACTIVITY: New activity notification.
        DUPLICATE_ACTIVITY: Duplicate activity notification.
        NEW_FOLLOWER_REQUEST: New follower request notification.
        NEW_FOLLOWER_REQUEST_ACCEPTED: Follower request accepted notification.
        GARMIN_TOKEN_EXPIRED: Garmin Connect account unlinked after its token expired.
        STRAVA_TOKEN_EXPIRED: Strava account unlinked after Strava rejected its token; carries ``delete_on``
            when Strava access was revoked and the Strava data is to be deleted that day.
        STRAVA_DATA_DELETED: Strava-synced activities and gear deleted after Strava access was revoked.
        IDP_LINKED: A sign-in provider was linked to the account.
        ACCOUNT_SECURITY_CHANGED: A security setting of the account changed.
        NEW_DEVICE_SIGN_IN: The account was signed in to from a new device.
        ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST: Admin sign-up approval request
            notification.
        ADMIN_USER_PROMOTED: A user was given administrator access; sent to the other active administrators.
    """

    NEW_ACTIVITY = ("new_activity", 1)
    DUPLICATE_ACTIVITY = ("duplicate_activity", 2)
    NEW_FOLLOWER_REQUEST = ("new_follower_request", 11)
    NEW_FOLLOWER_REQUEST_ACCEPTED = ("new_follower_request_accepted", 12)
    GARMIN_TOKEN_EXPIRED = ("garmin_token_expired", 21)
    STRAVA_TOKEN_EXPIRED = ("strava_token_expired", 22)
    STRAVA_DATA_DELETED = ("strava_data_deleted", 23)
    IDP_LINKED = ("idp_linked", 31)
    ACCOUNT_SECURITY_CHANGED = ("account_security_changed", 32)
    NEW_DEVICE_SIGN_IN = ("new_device_sign_in", 33)
    ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST = ("admin_new_sign_up_approval_request", 101)
    ADMIN_USER_PROMOTED = ("admin_user_promoted", 102)


# Websocket message types pushed to the browser alongside a stored notification.
NEW_ACTIVITY_WS_MESSAGE = "NEW_ACTIVITY_NOTIFICATION"
DUPLICATE_ACTIVITY_WS_MESSAGE = "NEW_DUPLICATE_ACTIVITY_START_TIME_NOTIFICATION"
NEW_FOLLOWER_REQUEST_WS_MESSAGE = "NEW_FOLLOWER_REQUEST_NOTIFICATION"
NEW_FOLLOWER_REQUEST_REMOVED_WS_MESSAGE = "NEW_FOLLOWER_REQUEST_REMOVED_NOTIFICATION"
NEW_FOLLOWER_REQUEST_ACCEPTED_WS_MESSAGE = "NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION"
GARMIN_UNLINKED_WS_MESSAGE = "GARMIN_TOKEN_EXPIRED_NOTIFICATION"
STRAVA_UNLINKED_WS_MESSAGE = "STRAVA_TOKEN_EXPIRED_NOTIFICATION"
STRAVA_DATA_DELETED_WS_MESSAGE = "STRAVA_DATA_DELETED_NOTIFICATION"
IDP_LINKED_WS_MESSAGE = "IDP_LINKED_NOTIFICATION"
ACCOUNT_SECURITY_CHANGED_WS_MESSAGE = "ACCOUNT_SECURITY_CHANGED_NOTIFICATION"
NEW_DEVICE_SIGN_IN_WS_MESSAGE = "NEW_DEVICE_SIGN_IN_NOTIFICATION"
ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_WS_MESSAGE = "ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_NOTIFICATION"
ADMIN_USER_PROMOTED_WS_MESSAGE = "ADMIN_USER_PROMOTED_NOTIFICATION"
