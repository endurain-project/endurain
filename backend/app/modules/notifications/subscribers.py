"""Consume activity, follower, identity-provider, sign-up, sign-in, MFA and user events to create user notifications."""

from collections.abc import Callable

import jasil.event_versioning as platform_event_versioning
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.events as activity_events
import modules.auth.account_security.events as account_security_events
import modules.auth.authentication.events as authentication_events
import modules.auth.identity_providers.events as idp_events
import modules.auth.known_devices.events as known_devices_events
import modules.auth.mfa_backup_codes.events as backup_codes_events
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.followers.events as followers_events
import modules.notifications.constants as notifications_constants
import modules.notifications.integration_service as notifications_integration
import modules.notifications.schema as notifications_schema
import modules.notifications.service as notifications_service
import modules.users.users.events as users_events
import modules.websocket.integration_service as websocket_integration

logger = core_logger.get_logger(__name__)

ACTIVITY_NOTIFICATION_SUBSCRIBER_ID = "activity.notify_created"
FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_requested"
FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID = "followers.notify_accepted"
FOLLOWER_REQUEST_REMOVED_NOTIFICATION_SUBSCRIBER_ID = "followers.clear_request_notification"
IDP_LINKED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_idp_linked"
ACCOUNT_SECURITY_CHANGED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_account_security_changed"
PASSWORD_RESET_COMPLETED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_password_reset_completed"  # noqa: S105 (name matches the password-secret heuristic, not a secret)
ACCOUNT_LOCKED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_account_locked"
MFA_LOCKED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_mfa_locked"
STEP_UP_SESSION_ENDED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_step_up_session_ended"
STEP_UP_LOCKED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_step_up_locked"
NEW_DEVICE_SIGN_IN_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_new_device_sign_in"
ADMIN_SIGN_UP_APPROVAL_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_admin_sign_up_approval"
BACKUP_CODE_USED_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_backup_code_used"
REFRESH_REUSE_NOTIFICATION_SUBSCRIBER_ID = "auth.notify_refresh_reuse"
ADMIN_USER_PROMOTED_NOTIFICATION_SUBSCRIBER_ID = "users.notify_admin_user_promoted"


def _notify_and_push(
    event: Event,
    recipient_user_id: int,
    create: Callable[[Session], tuple[notifications_schema.NotificationRead, str, bool]],
) -> bool:
    """Create a notification for an event and push it to the recipient.

    A user who no longer exists cannot be notified and a retry cannot change that,
    so the event is dropped instead of failing the durable job.

    Args:
        event: The event being handled, named in the log context.
        recipient_user_id: The user who owns the notification and receives the push.
        create: Stages and commits the notification on the given session.

    Returns:
        True when this call created the notification, False when it was skipped.
    """
    try:
        with core_database.SessionLocal() as db:
            notification, ws_message, created = create(db)
    except core_exceptions.NotFoundError:
        logger.warning(
            "Skipped notification for a user that no longer exists",
            extra=core_logger.context(event_id=event.event_id, event_type=event.event_type),
        )
        return False
    if not created:
        logger.debug(
            "Skipped duplicate notification",
            extra=core_logger.context(event_id=event.event_id, event_type=event.event_type),
        )
        return False
    notifications_integration.push_notification(recipient_user_id, notification, ws_message)
    return True


def notify_activity_created_for_event(event: Event) -> None:
    """Create the notification for a newly stored activity."""
    payload = platform_event_versioning.parse_payload(activity_events.ActivityCreatedPayload, event)
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_activity_created_notification(
            payload.user_id,
            payload.activity_id,
            payload.duplicate_start_time,
            event.event_id,
            db,
        ),
    )
    if created:
        logger.debug(
            "Created new-activity notification",
            extra=core_logger.context(activity_id=payload.activity_id, user_id=payload.user_id),
        )


def notify_follower_requested_for_event(event: Event) -> None:
    """Notify the target user of a new follow request."""
    payload = platform_event_versioning.parse_payload(followers_events.FollowerRequestedPayload, event)
    created = _notify_and_push(
        event,
        payload.target_user_id,
        lambda db: notifications_service.create_follow_request_notification(
            payload.requester_user_id,
            payload.target_user_id,
            event.event_id,
            db,
        ),
    )
    if created:
        logger.debug(
            "Created follow-request notification",
            extra=core_logger.context(
                requester_user_id=payload.requester_user_id,
                target_user_id=payload.target_user_id,
            ),
        )


def notify_follower_accepted_for_event(event: Event) -> None:
    """Notify the requester that their follow request was accepted."""
    payload = platform_event_versioning.parse_payload(followers_events.FollowerAcceptedPayload, event)
    created = _notify_and_push(
        event,
        payload.requester_user_id,
        lambda db: notifications_service.create_follow_accepted_notification(
            payload.accepter_user_id,
            payload.requester_user_id,
            event.event_id,
            db,
        ),
    )
    if created:
        logger.debug(
            "Created follow-accepted notification",
            extra=core_logger.context(
                accepter_user_id=payload.accepter_user_id,
                requester_user_id=payload.requester_user_id,
            ),
        )


def notify_idp_linked_for_event(event: Event) -> None:
    """Notify the user that a sign-in provider was linked to their account."""
    payload = platform_event_versioning.parse_payload(idp_events.IdpLinkedPayload, event)
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_idp_linked_notification(
            payload.user_id, payload.idp_id, event.event_id, db
        ),
    )
    if created:
        logger.debug(
            "Created identity-provider-linked notification",
            extra=core_logger.context(user_id=payload.user_id, idp_id=payload.idp_id),
        )


def notify_account_security_changed_for_event(event: Event) -> None:
    """Notify the user that a security setting of their account changed."""
    payload = platform_event_versioning.parse_payload(account_security_events.AccountSecurityChangedPayload, event)
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id,
            payload.change.value,
            payload.idp_id,
            event.event_id,
            db,
            access_type=payload.access_type,
        ),
    )
    if created:
        logger.debug(
            "Created account-security-changed notification",
            extra=core_logger.context(user_id=payload.user_id, change=payload.change.value),
        )


def notify_password_reset_completed_for_event(event: Event) -> None:
    """Notify the user that their password was reset through an emailed link."""
    payload = platform_event_versioning.parse_payload(password_reset_events.PasswordResetCompletedPayload, event)
    change = account_security_events.AccountSecurityChange.PASSWORD_RESET.value
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id, change, None, event.event_id, db
        ),
    )
    if created:
        logger.debug(
            "Created password-reset-completed notification", extra=core_logger.context(user_id=payload.user_id)
        )


def notify_account_locked_for_event(event: Event) -> None:
    """Notify the user that repeated failed sign-ins locked their account."""
    payload = platform_event_versioning.parse_payload(authentication_events.AccountLockedPayload, event)
    change = account_security_events.AccountSecurityChange.ACCOUNT_LOCKED.value
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id, change, None, event.event_id, db
        ),
    )
    if created:
        logger.debug("Created account-locked notification", extra=core_logger.context(user_id=payload.user_id))


def notify_mfa_locked_for_event(event: Event) -> None:
    """Notify the user that wrong two-step verification codes locked their sign-in."""
    payload = platform_event_versioning.parse_payload(authentication_events.MfaLockedPayload, event)
    change = account_security_events.AccountSecurityChange.MFA_LOCKED.value
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id, change, None, event.event_id, db
        ),
    )
    if created:
        logger.debug("Created MFA-locked notification", extra=core_logger.context(user_id=payload.user_id))


def notify_step_up_session_ended_for_event(event: Event) -> None:
    """Notify the user that repeated failed step-ups ended one of their sessions."""
    payload = platform_event_versioning.parse_payload(account_security_events.StepUpSessionEndedPayload, event)
    change = account_security_events.AccountSecurityChange.STEP_UP_SESSION_ENDED.value
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id, change, None, event.event_id, db
        ),
    )
    if created:
        logger.debug("Created step-up-session-ended notification", extra=core_logger.context(user_id=payload.user_id))


def notify_step_up_locked_for_event(event: Event) -> None:
    """Notify the user that repeated failed step-ups locked step-up for their account."""
    payload = platform_event_versioning.parse_payload(account_security_events.StepUpLockedPayload, event)
    change = account_security_events.AccountSecurityChange.STEP_UP_LOCKED.value
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id, change, None, event.event_id, db
        ),
    )
    if created:
        logger.debug("Created step-up-locked notification", extra=core_logger.context(user_id=payload.user_id))


def notify_new_device_sign_in_for_event(event: Event) -> None:
    """Notify the user that their account was signed in to from a new device."""
    payload = platform_event_versioning.parse_payload(known_devices_events.NewDeviceSignInPayload, event)
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_new_device_sign_in_notification(
            payload.user_id, payload.browser, payload.operating_system, payload.ip_address, event.event_id, db
        ),
    )
    if created:
        logger.debug("Created new-device sign-in notification", extra=core_logger.context(user_id=payload.user_id))


def notify_admin_sign_up_approval_for_event(event: Event) -> None:
    """Notify an admin that a new sign-up awaits their approval."""
    payload = platform_event_versioning.parse_payload(sign_up_events.SignUpApprovalRequestedPayload, event)
    created = _notify_and_push(
        event,
        payload.admin_user_id,
        lambda db: notifications_service.create_admin_sign_up_approval_notification(
            payload.user_id, payload.admin_user_id, event.event_id, db
        ),
    )
    if created:
        logger.debug(
            "Created sign-up approval notification",
            extra=core_logger.context(user_id=payload.user_id, admin_user_id=payload.admin_user_id),
        )


def notify_backup_code_used_for_event(event: Event) -> None:
    """Notify the user that a backup code was used on their account and how many are left."""
    payload = platform_event_versioning.parse_payload(backup_codes_events.BackupCodeUsedPayload, event)
    change = account_security_events.AccountSecurityChange.BACKUP_CODE_USED.value
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id,
            change,
            None,
            event.event_id,
            db,
            backup_codes_remaining=payload.backup_codes_remaining,
        ),
    )
    if created:
        logger.debug("Created backup-code-used notification", extra=core_logger.context(user_id=payload.user_id))


def notify_refresh_reuse_for_event(event: Event) -> None:
    """Notify the user that a reused refresh token ended one of their sessions."""
    payload = platform_event_versioning.parse_payload(authentication_events.RefreshReuseDetectedPayload, event)
    change = account_security_events.AccountSecurityChange.REFRESH_TOKEN_REUSE_DETECTED.value
    created = _notify_and_push(
        event,
        payload.user_id,
        lambda db: notifications_service.create_account_security_changed_notification(
            payload.user_id, change, None, event.event_id, db
        ),
    )
    if created:
        logger.debug("Created refresh-reuse notification", extra=core_logger.context(user_id=payload.user_id))


def notify_admin_user_promoted_for_event(event: Event) -> None:
    """Notify an admin that a user was given administrator access."""
    payload = platform_event_versioning.parse_payload(users_events.AdminPromotedPayload, event)
    created = _notify_and_push(
        event,
        payload.admin_user_id,
        lambda db: notifications_service.create_admin_user_promoted_notification(
            payload.user_id, payload.admin_user_id, event.event_id, db
        ),
    )
    if created:
        logger.debug(
            "Created admin-promoted notification",
            extra=core_logger.context(user_id=payload.user_id, admin_user_id=payload.admin_user_id),
        )


def clear_follower_request_notification_for_event(event: Event) -> None:
    """Take back the follow-request notification once the request is gone unaccepted.

    Deleting is idempotent, so a redelivered event finds nothing left to delete.
    """
    payload = platform_event_versioning.parse_payload(followers_events.FollowerRequestRemovedPayload, event)
    with core_database.SessionLocal() as db:
        deleted = notifications_service.remove_follow_request_notifications(
            payload.requester_user_id, payload.target_user_id, db
        )
    if not deleted:
        return
    websocket_integration.push_to_user(
        payload.target_user_id, {"message": notifications_constants.NEW_FOLLOWER_REQUEST_REMOVED_WS_MESSAGE}
    )
    logger.debug(
        "Removed follow-request notification",
        extra=core_logger.context(
            requester_user_id=payload.requester_user_id,
            target_user_id=payload.target_user_id,
        ),
    )


on_activity_created_notify = best_effort(notify_activity_created_for_event)
on_follower_requested_notify = best_effort(notify_follower_requested_for_event)
on_follower_accepted_notify = best_effort(notify_follower_accepted_for_event)
on_follower_request_removed_clear = best_effort(clear_follower_request_notification_for_event)
on_idp_linked_notify = best_effort(notify_idp_linked_for_event)
on_account_security_changed_notify = best_effort(notify_account_security_changed_for_event)
on_password_reset_completed_notify = best_effort(notify_password_reset_completed_for_event)
on_account_locked_notify = best_effort(notify_account_locked_for_event)
on_mfa_locked_notify = best_effort(notify_mfa_locked_for_event)
on_step_up_session_ended_notify = best_effort(notify_step_up_session_ended_for_event)
on_step_up_locked_notify = best_effort(notify_step_up_locked_for_event)
on_new_device_sign_in_notify = best_effort(notify_new_device_sign_in_for_event)
on_admin_sign_up_approval_notify = best_effort(notify_admin_sign_up_approval_for_event)
on_backup_code_used_notify = best_effort(notify_backup_code_used_for_event)
on_refresh_reuse_notify = best_effort(notify_refresh_reuse_for_event)
on_admin_user_promoted_notify = best_effort(notify_admin_user_promoted_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register every notification event consumer on the running bus."""
    events.subscribe(activity_events.ACTIVITY_CREATED, on_activity_created_notify)
    events.subscribe(followers_events.FOLLOWER_REQUESTED, on_follower_requested_notify)
    events.subscribe(followers_events.FOLLOWER_ACCEPTED, on_follower_accepted_notify)
    events.subscribe(followers_events.FOLLOWER_REQUEST_REMOVED, on_follower_request_removed_clear)
    events.subscribe(idp_events.IDP_LINKED, on_idp_linked_notify)
    events.subscribe(account_security_events.ACCOUNT_SECURITY_CHANGED, on_account_security_changed_notify)
    events.subscribe(password_reset_events.PASSWORD_RESET_COMPLETED, on_password_reset_completed_notify)
    events.subscribe(authentication_events.ACCOUNT_LOCKED, on_account_locked_notify)
    events.subscribe(authentication_events.MFA_LOCKED, on_mfa_locked_notify)
    events.subscribe(account_security_events.STEP_UP_SESSION_ENDED, on_step_up_session_ended_notify)
    events.subscribe(account_security_events.STEP_UP_LOCKED, on_step_up_locked_notify)
    events.subscribe(known_devices_events.NEW_DEVICE_SIGN_IN, on_new_device_sign_in_notify)
    events.subscribe(sign_up_events.SIGN_UP_APPROVAL_REQUESTED, on_admin_sign_up_approval_notify)
    events.subscribe(backup_codes_events.BACKUP_CODE_USED, on_backup_code_used_notify)
    events.subscribe(authentication_events.REFRESH_REUSE_DETECTED, on_refresh_reuse_notify)
    events.subscribe(users_events.USERS_ADMIN_PROMOTED, on_admin_user_promoted_notify)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register every retryable notification event consumer."""
    registry.register(
        activity_events.ACTIVITY_CREATED,
        ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
        notify_activity_created_for_event,
    )
    registry.register(
        followers_events.FOLLOWER_REQUESTED,
        FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID,
        notify_follower_requested_for_event,
    )
    registry.register(
        followers_events.FOLLOWER_ACCEPTED,
        FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID,
        notify_follower_accepted_for_event,
    )
    registry.register(
        followers_events.FOLLOWER_REQUEST_REMOVED,
        FOLLOWER_REQUEST_REMOVED_NOTIFICATION_SUBSCRIBER_ID,
        clear_follower_request_notification_for_event,
    )
    registry.register(
        idp_events.IDP_LINKED,
        IDP_LINKED_NOTIFICATION_SUBSCRIBER_ID,
        notify_idp_linked_for_event,
    )
    registry.register(
        account_security_events.ACCOUNT_SECURITY_CHANGED,
        ACCOUNT_SECURITY_CHANGED_NOTIFICATION_SUBSCRIBER_ID,
        notify_account_security_changed_for_event,
    )
    registry.register(
        password_reset_events.PASSWORD_RESET_COMPLETED,
        PASSWORD_RESET_COMPLETED_NOTIFICATION_SUBSCRIBER_ID,
        notify_password_reset_completed_for_event,
    )
    registry.register(
        authentication_events.ACCOUNT_LOCKED,
        ACCOUNT_LOCKED_NOTIFICATION_SUBSCRIBER_ID,
        notify_account_locked_for_event,
    )
    registry.register(
        authentication_events.MFA_LOCKED,
        MFA_LOCKED_NOTIFICATION_SUBSCRIBER_ID,
        notify_mfa_locked_for_event,
    )
    registry.register(
        account_security_events.STEP_UP_SESSION_ENDED,
        STEP_UP_SESSION_ENDED_NOTIFICATION_SUBSCRIBER_ID,
        notify_step_up_session_ended_for_event,
    )
    registry.register(
        account_security_events.STEP_UP_LOCKED,
        STEP_UP_LOCKED_NOTIFICATION_SUBSCRIBER_ID,
        notify_step_up_locked_for_event,
    )
    registry.register(
        known_devices_events.NEW_DEVICE_SIGN_IN,
        NEW_DEVICE_SIGN_IN_NOTIFICATION_SUBSCRIBER_ID,
        notify_new_device_sign_in_for_event,
    )
    registry.register(
        sign_up_events.SIGN_UP_APPROVAL_REQUESTED,
        ADMIN_SIGN_UP_APPROVAL_NOTIFICATION_SUBSCRIBER_ID,
        notify_admin_sign_up_approval_for_event,
    )
    registry.register(
        backup_codes_events.BACKUP_CODE_USED,
        BACKUP_CODE_USED_NOTIFICATION_SUBSCRIBER_ID,
        notify_backup_code_used_for_event,
    )
    registry.register(
        authentication_events.REFRESH_REUSE_DETECTED,
        REFRESH_REUSE_NOTIFICATION_SUBSCRIBER_ID,
        notify_refresh_reuse_for_event,
    )
    registry.register(
        users_events.USERS_ADMIN_PROMOTED,
        ADMIN_USER_PROMOTED_NOTIFICATION_SUBSCRIBER_ID,
        notify_admin_user_promoted_for_event,
    )
