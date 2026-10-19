"""Event subscribers for the sign-up tokens module."""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider
from jasil.subscribers import best_effort

import core.database as core_database
import modules.auth.sign_up_tokens.events as sign_up_tokens_events
import modules.auth.sign_up_tokens.utils as sign_up_tokens_utils

SIGN_UP_VERIFICATION_EMAIL_SUBSCRIBER_ID = "auth.send_sign_up_verification_email"
SIGN_UP_APPROVAL_REQUEST_EMAIL_SUBSCRIBER_ID = "auth.send_sign_up_approval_request_email"
SIGN_UP_APPROVED_EMAIL_SUBSCRIBER_ID = "auth.send_sign_up_approved_email"


def send_verification_email_for_event(event: Event) -> None:
    """Send the verification email for an ``auth.sign_up_verification_requested`` event.

    Raises:
        MailError: On a transient delivery failure, so the durable job is retried.
    """
    payload = platform_event_versioning.parse_payload(sign_up_tokens_events.SignUpUserPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        sign_up_tokens_utils.send_sign_up_verification_email_to_user(payload.user_id, mail, db)


def send_approval_request_email_for_event(event: Event) -> None:
    """Send the admin approval request for an ``auth.sign_up_approval_requested`` event.

    Raises:
        MailError: On a transient delivery failure, so the durable job is retried.
    """
    payload = platform_event_versioning.parse_payload(sign_up_tokens_events.SignUpApprovalRequestedPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        sign_up_tokens_utils.send_sign_up_approval_request_email_to_admin(
            payload.user_id, payload.admin_user_id, mail, db
        )


def send_approved_email_for_event(event: Event) -> None:
    """Send the approval notice for an ``auth.sign_up_approved`` event.

    Raises:
        MailError: On a transient delivery failure, so the durable job is retried.
    """
    payload = platform_event_versioning.parse_payload(sign_up_tokens_events.SignUpUserPayload, event)
    mail = platform_runtime.get_active_platform().mail
    with core_database.SessionLocal() as db:
        sign_up_tokens_utils.send_sign_up_approved_email_to_user(payload.user_id, mail, db)


on_sign_up_verification_requested = best_effort(send_verification_email_for_event)
on_sign_up_approval_requested = best_effort(send_approval_request_email_for_event)
on_sign_up_approved = best_effort(send_approved_email_for_event)


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the sign-up event consumers on the running bus."""
    events.subscribe(sign_up_tokens_events.SIGN_UP_VERIFICATION_REQUESTED, on_sign_up_verification_requested)
    events.subscribe(sign_up_tokens_events.SIGN_UP_APPROVAL_REQUESTED, on_sign_up_approval_requested)
    events.subscribe(sign_up_tokens_events.SIGN_UP_APPROVED, on_sign_up_approved)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the retryable sign-up event consumers."""
    registry.register(
        sign_up_tokens_events.SIGN_UP_VERIFICATION_REQUESTED,
        SIGN_UP_VERIFICATION_EMAIL_SUBSCRIBER_ID,
        send_verification_email_for_event,
    )
    registry.register(
        sign_up_tokens_events.SIGN_UP_APPROVAL_REQUESTED,
        SIGN_UP_APPROVAL_REQUEST_EMAIL_SUBSCRIBER_ID,
        send_approval_request_email_for_event,
    )
    registry.register(
        sign_up_tokens_events.SIGN_UP_APPROVED,
        SIGN_UP_APPROVED_EMAIL_SUBSCRIBER_ID,
        send_approved_email_for_event,
    )
