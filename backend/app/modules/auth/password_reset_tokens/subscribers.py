"""Event subscribers for password-reset email delivery."""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.config as core_config
import core.database as core_database
import core.logger as core_logger
import core.mail as core_mail
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.password_reset_tokens.service as password_reset_service

logger = core_logger.get_logger(__name__)
PASSWORD_RESET_EMAIL_SUBSCRIBER_ID = "auth.send_password_reset_email"  # noqa: S105


def send_password_reset_email_for_event(event: Event) -> None:
    """Prepare and deliver the email for a password-reset request event."""
    payload = platform_event_versioning.parse_payload(password_reset_events.PasswordResetRequestedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    frontend_host = core_config.settings.ENDURAIN_HOST
    with core_database.SessionLocal() as db:
        message = password_reset_service.prepare_password_reset_email(
            payload.user_id, event.event_id, frontend_host, db
        )
    if message is None:
        logger.debug("Skipped password-reset email because the user is missing or inactive")
        return
    recipient, subject, html_content, text_content = message
    try:
        sent = core_mail.send_email(mail, recipient, subject, html_content, text_content)
    except Exception as err:
        logger.error("Password-reset email delivery failed", exc_info=err)
        raise
    if sent:
        logger.debug("Password-reset email delivered")
    else:
        logger.debug("Password-reset email was not delivered")
    logger.debug("Password-reset email event processed", extra=core_logger.context(user_id=payload.user_id))


on_password_reset_requested = best_effort(send_password_reset_email_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the password reset event consumers on the running bus."""
    events.subscribe(password_reset_events.PASSWORD_RESET_REQUESTED, on_password_reset_requested)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable password reset event consumers."""
    registry.register(
        password_reset_events.PASSWORD_RESET_REQUESTED,
        PASSWORD_RESET_EMAIL_SUBSCRIBER_ID,
        send_password_reset_email_for_event,
    )
