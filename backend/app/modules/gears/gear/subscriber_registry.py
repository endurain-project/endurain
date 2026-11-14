"""Durable command registration for the gear package."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry

import modules.gears.gear.subscribers as gears_subscribers


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the gear command handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    gears_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        gears_subscribers.DELETION_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "The gear row is the source of truth and the deletion only touches what still carries the gear, so "
            "the user deletes it again; a stuck claim expires after an hour."
        ),
    ),
)
