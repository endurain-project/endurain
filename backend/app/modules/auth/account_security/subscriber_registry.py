"""Registration surface and reconciliation declarations for account-security emails."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.auth.account_security.subscribers as account_security_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the account-security bus subscribers."""
    account_security_subscribers.register_bus_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the account-security durable handlers."""
    account_security_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        account_security_subscribers.ACCOUNT_SECURITY_CHANGED_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A security notice is a one-off reaction to a change that is already stored and audited; "
            "nothing is left to backfill once the change is made."
        ),
    ),
    DurableSubscriberNet(
        account_security_subscribers.IDP_LINKED_EMAIL_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A link notice is a one-off reaction to a link row that is already stored; "
            "nothing is left to backfill once the link is made."
        ),
    ),
)
