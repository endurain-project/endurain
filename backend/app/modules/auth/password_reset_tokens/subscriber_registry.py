"""Registration surface and reconciliation declarations for password reset emails."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.auth.password_reset_tokens.subscribers as password_reset_tokens_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the password reset bus subscribers."""
    password_reset_tokens_subscribers.register_bus_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the password reset durable handlers."""
    password_reset_tokens_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        password_reset_tokens_subscribers.PASSWORD_RESET_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A reset email is a transient reaction to a user request; a lost one is recovered by "
            "the user requesting a new reset link."
        ),
    ),
)
