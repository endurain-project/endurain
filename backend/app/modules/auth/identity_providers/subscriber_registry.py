"""Registration surface and reconciliation declarations for identity-provider token refresh."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.auth.identity_providers.subscribers as idp_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the identity-provider bus subscribers."""
    idp_subscribers.register_bus_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the identity-provider durable handlers."""
    idp_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        idp_subscribers.IDP_TOKEN_REFRESH_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The refresh is opportunistic: every session refresh re-evaluates the stored tokens and "
            "queues it again, and the link rows hold the state it acts on."
        ),
    ),
)
