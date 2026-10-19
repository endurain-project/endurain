"""Event subscribers for the password reset tokens module."""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.database as core_database
import modules.auth.password_reset_tokens.events as password_reset_tokens_events
import modules.auth.password_reset_tokens.utils as password_reset_tokens_utils

PASSWORD_RESET_EMAIL_SUBSCRIBER_ID = "auth.send_password_reset_email"  # noqa: S105 (subscriber id, not a password)


def send_password_reset_email_for_event(event: Event) -> None:
    """Send the password reset email for a ``auth.password_reset_requested`` event.

    Raises:
        MailError: On a transient delivery failure, so the durable job is retried.
    """
    payload = platform_event_versioning.parse_payload(password_reset_tokens_events.PasswordResetRequestedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        password_reset_tokens_utils.send_password_reset_email_to_user(payload.user_id, mail, db)


on_password_reset_requested = best_effort(send_password_reset_email_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the password reset event consumers on the running bus."""
    events.subscribe(password_reset_tokens_events.PASSWORD_RESET_REQUESTED, on_password_reset_requested)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable password reset event consumers."""
    registry.register(
        password_reset_tokens_events.PASSWORD_RESET_REQUESTED,
        PASSWORD_RESET_EMAIL_SUBSCRIBER_ID,
        send_password_reset_email_for_event,
    )
