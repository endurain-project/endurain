"""
Notifications module for user notification management.

This module handles the creation, retrieval, and management of user
notifications including activity alerts, follower requests, and admin approval
notifications.

Exports:
    - CRUD: get_user_notification_by_id, get_user_notifications_count,
        get_user_notifications_with_pagination,
        create_notification, mark_notification_as_read
    - Schemas: NotificationBase, NotificationCreate, NotificationRead
    - Constants: NotificationType
    - Utils: create_new_activity_notification,
        create_new_duplicate_start_time_activity_notification,
        create_new_follower_request_notification,
        create_accepted_follower_request_notification,
        create_admin_new_sign_up_approval_request_notification
"""

from .constants import NotificationType
from .crud import (
    create_notification,
    get_user_notification_by_id,
    get_user_notifications_count,
    get_user_notifications_with_pagination,
    mark_notification_as_read,
)
from .schema import (
    NotificationBase,
    NotificationCreate,
    NotificationRead,
)
from .utils import (
    create_accepted_follower_request_notification,
    create_admin_new_sign_up_approval_request_notification,
    create_new_activity_notification,
    create_new_duplicate_start_time_activity_notification,
    create_new_follower_request_notification,
)

__all__ = [
    "NotificationBase",
    "NotificationCreate",
    "NotificationRead",
    "NotificationType",
    "create_accepted_follower_request_notification",
    "create_admin_new_sign_up_approval_request_notification",
    "create_new_activity_notification",
    "create_new_duplicate_start_time_activity_notification",
    "create_new_follower_request_notification",
    "create_notification",
    "get_user_notification_by_id",
    "get_user_notifications_count",
    "get_user_notifications_with_pagination",
    "mark_notification_as_read",
]
