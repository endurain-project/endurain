"""Registration surface and reconciliation declarations for the profile import."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.users.users_profile.subscribers as profile_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register the profile import bus subscribers.

    Args:
        events: The event bus.
    """
    profile_subscribers.register_bus_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the profile import durable handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    profile_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        profile_subscribers.IMPORT_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "An import is a command, not derived state. Its outcome is recorded in the shared import "
            "state, which the client polls, and a failed import is re-run by the user."
        ),
    ),
    DurableSubscriberNet(
        profile_subscribers.EXPORT_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "An export is a command, not derived state. Its outcome is recorded in the shared export "
            "state, which the client polls, and a failed export is re-requested by the user."
        ),
    ),
)
