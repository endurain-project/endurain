"""Registration surface and reconciliation declarations for sign-up emails."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.auth.sign_up_tokens.subscribers as sign_up_tokens_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the sign-up bus subscribers."""
    sign_up_tokens_subscribers.register_bus_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the sign-up durable handlers."""
    sign_up_tokens_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        sign_up_tokens_subscribers.SIGN_UP_VERIFICATION_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A verification email is a transient reaction to a sign-up; the user and token rows are the "
            "source of truth and a lost email is recovered by an admin or by signing up again."
        ),
    ),
    DurableSubscriberNet(
        sign_up_tokens_subscribers.EMAIL_CHANGE_VERIFICATION_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A verification email is a transient reaction to an email change; the user row is the source "
            "of truth and a lost email is recovered by changing the address again or by an admin."
        ),
    ),
    DurableSubscriberNet(
        sign_up_tokens_subscribers.SIGN_UP_APPROVAL_REQUEST_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The pending user row is the source of truth; admins also see the pending sign-up in the "
            "users list and in an in-app notification."
        ),
    ),
    DurableSubscriberNet(
        sign_up_tokens_subscribers.SIGN_UP_APPROVED_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason="The approved user row is the source of truth; the email is a courtesy notice.",
    ),
    DurableSubscriberNet(
        sign_up_tokens_subscribers.SIGN_UP_EXISTING_ACCOUNT_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason="The notice is a courtesy to the address owner; the account is unchanged.",
    ),
)
