"""Event subscribers for account-security change, password-reset and new-device sign-in emails."""

from collections.abc import Callable

import jasil.event_versioning as platform_event_versioning
import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import core.mail as core_mail
import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.account_security.email_messages as account_security_email_messages
import modules.auth.account_security.events as account_security_events
import modules.auth.identity_providers.events as idp_events
import modules.auth.known_devices.events as known_devices_events
import modules.auth.password_reset_tokens.events as password_reset_events

logger = core_logger.get_logger(__name__)
ACCOUNT_SECURITY_CHANGED_EMAIL_SUBSCRIBER_ID = "auth.send_account_security_changed_email"
IDP_LINKED_EMAIL_SUBSCRIBER_ID = "auth.send_idp_linked_email"
NEW_DEVICE_SIGN_IN_EMAIL_SUBSCRIBER_ID = "auth.send_new_device_sign_in_email"
PASSWORD_RESET_COMPLETED_EMAIL_SUBSCRIBER_ID = "auth.send_password_reset_completed_email"  # noqa: S105 (name matches the password-secret heuristic, not a secret)


def _send_security_email(
    user_id: int,
    change: str,
    prepare: Callable[[Session], tuple[str, str, str, str] | None],
    mail: platform_providers.MailProvider,
) -> None:
    """Prepare a security email in a short session and send it once the session has closed.

    Args:
        user_id: The user the email is about.
        change: What the email reports, named in the log context.
        prepare: Returns the recipient, subject, HTML and text from the session, or None to send nothing.
        mail: The mail provider that delivers the email.
    """
    with core_database.SessionLocal() as db:
        message = prepare(db)
    if message is None:
        logger.debug(
            "Skipped security email because the user is missing or inactive",
            extra=core_logger.context(user_id=user_id, change=change),
        )
        return
    recipient, subject, html_content, text_content = message
    try:
        sent = core_mail.send_email(mail, recipient, subject, html_content, text_content)
    except Exception as err:
        logger.error(
            "Security email delivery failed",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, change=change),
        )
        raise
    logger.debug(
        "Security email delivered" if sent else "Security email was not delivered",
        extra=core_logger.context(user_id=user_id, change=change),
    )


def send_security_changed_email_for_event(event: Event) -> None:
    """Send the user an email naming the account-security change that happened."""
    payload = platform_event_versioning.parse_payload(account_security_events.AccountSecurityChangedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    _send_security_email(
        payload.user_id,
        payload.change.value,
        lambda db: account_security_service.prepare_security_change_email(
            payload.user_id, payload.change.value, payload.idp_id, core_config.settings.ENDURAIN_HOST, db
        ),
        mail,
    )
    logger.debug(
        "Account-security-changed event processed",
        extra=core_logger.context(user_id=payload.user_id, change=payload.change.value),
    )


def send_idp_linked_email_for_event(event: Event) -> None:
    """Send the user an email saying a sign-in provider was linked to their account."""
    payload = platform_event_versioning.parse_payload(idp_events.IdpLinkedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    change = account_security_email_messages.IDENTITY_PROVIDER_LINKED
    _send_security_email(
        payload.user_id,
        change,
        lambda db: account_security_service.prepare_security_change_email(
            payload.user_id, change, payload.idp_id, core_config.settings.ENDURAIN_HOST, db
        ),
        mail,
    )
    logger.debug("Identity-provider-linked event processed", extra=core_logger.context(user_id=payload.user_id))


def send_password_reset_completed_email_for_event(event: Event) -> None:
    """Send the user an email saying their password was reset through an emailed link."""
    payload = platform_event_versioning.parse_payload(password_reset_events.PasswordResetCompletedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    change = account_security_events.AccountSecurityChange.PASSWORD_RESET.value
    _send_security_email(
        payload.user_id,
        change,
        lambda db: account_security_service.prepare_security_change_email(
            payload.user_id, change, None, core_config.settings.ENDURAIN_HOST, db
        ),
        mail,
    )
    logger.debug("Password-reset-completed event processed", extra=core_logger.context(user_id=payload.user_id))


def send_new_device_sign_in_email_for_event(event: Event) -> None:
    """Send the user an email saying their account was signed in to from a new device."""
    payload = platform_event_versioning.parse_payload(known_devices_events.NewDeviceSignInPayload, event)
    mail = platform_runtime.get_active_platform().mail
    _send_security_email(
        payload.user_id,
        known_devices_events.NEW_DEVICE_SIGN_IN,
        lambda db: account_security_service.prepare_new_device_sign_in_email(
            payload.user_id,
            payload.browser,
            payload.operating_system,
            payload.ip_address,
            payload.method.value,
            payload.signed_in_at,
            core_config.settings.ENDURAIN_HOST,
            db,
        ),
        mail,
    )
    logger.debug("New-device sign-in event processed", extra=core_logger.context(user_id=payload.user_id))


on_security_changed = best_effort(send_security_changed_email_for_event)
on_idp_linked = best_effort(send_idp_linked_email_for_event)
on_password_reset_completed = best_effort(send_password_reset_completed_email_for_event)
on_new_device_sign_in = best_effort(send_new_device_sign_in_email_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the account-security and new-device sign-in email bus subscribers."""
    events.subscribe(account_security_events.ACCOUNT_SECURITY_CHANGED, on_security_changed)
    events.subscribe(idp_events.IDP_LINKED, on_idp_linked)
    events.subscribe(password_reset_events.PASSWORD_RESET_COMPLETED, on_password_reset_completed)
    events.subscribe(known_devices_events.NEW_DEVICE_SIGN_IN, on_new_device_sign_in)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable account-security and new-device sign-in email durable handlers."""
    registry.register(
        account_security_events.ACCOUNT_SECURITY_CHANGED,
        ACCOUNT_SECURITY_CHANGED_EMAIL_SUBSCRIBER_ID,
        send_security_changed_email_for_event,
    )
    registry.register(
        idp_events.IDP_LINKED,
        IDP_LINKED_EMAIL_SUBSCRIBER_ID,
        send_idp_linked_email_for_event,
    )
    registry.register(
        password_reset_events.PASSWORD_RESET_COMPLETED,
        PASSWORD_RESET_COMPLETED_EMAIL_SUBSCRIBER_ID,
        send_password_reset_completed_email_for_event,
    )
    registry.register(
        known_devices_events.NEW_DEVICE_SIGN_IN,
        NEW_DEVICE_SIGN_IN_EMAIL_SUBSCRIBER_ID,
        send_new_device_sign_in_email_for_event,
    )
