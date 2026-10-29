"""Event subscribers for sign-up email delivery."""

import jasil.event_versioning as platform_event_versioning
import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import core.mail as core_mail
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.service as sign_up_service

logger = core_logger.get_logger(__name__)
SIGN_UP_VERIFICATION_EMAIL_SUBSCRIBER_ID = "auth.send_sign_up_verification_email"
EMAIL_CHANGE_VERIFICATION_EMAIL_SUBSCRIBER_ID = "auth.send_email_change_verification_email"
SIGN_UP_APPROVAL_REQUEST_EMAIL_SUBSCRIBER_ID = "auth.send_sign_up_approval_request_email"
SIGN_UP_APPROVED_EMAIL_SUBSCRIBER_ID = "auth.send_sign_up_approved_email"
SIGN_UP_EXISTING_ACCOUNT_EMAIL_SUBSCRIBER_ID = "auth.send_sign_up_existing_account_email"


def _deliver_email(
    mail: platform_providers.MailProvider,
    message: tuple[str, str, str, str] | None,
    event_name: str,
) -> None:
    """Send a prepared email after its database session has closed."""
    if message is None:
        logger.debug(
            "Skipped sign-up email because a recipient record is missing", extra=core_logger.context(kind=event_name)
        )
        return
    recipient, subject, html_content, text_content = message
    try:
        sent = core_mail.send_email(mail, recipient, subject, html_content, text_content)
    except Exception as err:
        logger.error("Sign-up email delivery failed", exc_info=err, extra=core_logger.context(kind=event_name))
        raise
    if sent:
        logger.debug("Sign-up email delivered", extra=core_logger.context(kind=event_name))
    else:
        logger.debug("Sign-up email was not delivered", extra=core_logger.context(kind=event_name))


def send_verification_email_for_event(event: Event) -> None:
    """Send the verification email for a sign-up event."""
    payload = platform_event_versioning.parse_payload(sign_up_events.SignUpUserPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        message = sign_up_service.prepare_sign_up_verification_email(
            payload.user_id,
            core_config.settings.ENDURAIN_HOST,
            db,
        )
    _deliver_email(mail, message, "verification")
    logger.debug("Sign-up verification event processed", extra=core_logger.context(user_id=payload.user_id))


def send_email_change_verification_email_for_event(event: Event) -> None:
    """Send the verification email for a changed email address."""
    payload = platform_event_versioning.parse_payload(sign_up_events.SignUpUserPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        message = sign_up_service.prepare_email_change_verification_email(
            payload.user_id,
            core_config.settings.ENDURAIN_HOST,
            db,
        )
    _deliver_email(mail, message, "email-change-verification")
    logger.debug("Email-change verification event processed", extra=core_logger.context(user_id=payload.user_id))


def send_approval_request_email_for_event(event: Event) -> None:
    """Send the admin approval request for a sign-up event."""
    payload = platform_event_versioning.parse_payload(sign_up_events.SignUpApprovalRequestedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        message = sign_up_service.prepare_sign_up_approval_request_email(
            payload.user_id,
            payload.admin_user_id,
            core_config.settings.ENDURAIN_HOST,
            db,
        )
    _deliver_email(mail, message, "approval-request")
    logger.debug("Sign-up approval-request event processed", extra=core_logger.context(user_id=payload.user_id))


def send_approved_email_for_event(event: Event) -> None:
    """Send the approval notice for a sign-up event."""
    payload = platform_event_versioning.parse_payload(sign_up_events.SignUpUserPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        message = sign_up_service.prepare_sign_up_approved_email(
            payload.user_id,
            core_config.settings.ENDURAIN_HOST,
            db,
        )
    _deliver_email(mail, message, "approved")
    logger.debug("Sign-up approved event processed", extra=core_logger.context(user_id=payload.user_id))


def send_existing_account_email_for_event(event: Event) -> None:
    """Send the notice to the owner of an email address a sign-up reused."""
    payload = platform_event_versioning.parse_payload(sign_up_events.SignUpUserPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        message = sign_up_service.prepare_sign_up_existing_account_email(
            payload.user_id,
            core_config.settings.ENDURAIN_HOST,
            db,
        )
    _deliver_email(mail, message, "existing-account")
    logger.debug("Sign-up existing-account event processed", extra=core_logger.context(user_id=payload.user_id))


on_sign_up_verification_requested = best_effort(send_verification_email_for_event)
on_email_change_verification_requested = best_effort(send_email_change_verification_email_for_event)
on_sign_up_approval_requested = best_effort(send_approval_request_email_for_event)
on_sign_up_approved = best_effort(send_approved_email_for_event)
on_sign_up_existing_account = best_effort(send_existing_account_email_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the sign-up bus subscribers."""
    events.subscribe(sign_up_events.SIGN_UP_VERIFICATION_REQUESTED, on_sign_up_verification_requested)
    events.subscribe(sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED, on_email_change_verification_requested)
    events.subscribe(sign_up_events.SIGN_UP_APPROVAL_REQUESTED, on_sign_up_approval_requested)
    events.subscribe(sign_up_events.SIGN_UP_APPROVED, on_sign_up_approved)
    events.subscribe(sign_up_events.SIGN_UP_EXISTING_ACCOUNT, on_sign_up_existing_account)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable sign-up durable handlers."""
    registry.register(
        sign_up_events.SIGN_UP_VERIFICATION_REQUESTED,
        SIGN_UP_VERIFICATION_EMAIL_SUBSCRIBER_ID,
        send_verification_email_for_event,
    )
    registry.register(
        sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
        EMAIL_CHANGE_VERIFICATION_EMAIL_SUBSCRIBER_ID,
        send_email_change_verification_email_for_event,
    )
    registry.register(
        sign_up_events.SIGN_UP_APPROVAL_REQUESTED,
        SIGN_UP_APPROVAL_REQUEST_EMAIL_SUBSCRIBER_ID,
        send_approval_request_email_for_event,
    )
    registry.register(
        sign_up_events.SIGN_UP_APPROVED,
        SIGN_UP_APPROVED_EMAIL_SUBSCRIBER_ID,
        send_approved_email_for_event,
    )
    registry.register(
        sign_up_events.SIGN_UP_EXISTING_ACCOUNT,
        SIGN_UP_EXISTING_ACCOUNT_EMAIL_SUBSCRIBER_ID,
        send_existing_account_email_for_event,
    )
