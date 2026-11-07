"""Durable command registration for the Garmin Connect module."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry

import modules.garmin.subscribers as garmin_subscribers


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the Garmin Connect command handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    garmin_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        garmin_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A sync is a command to re-read a Garmin Connect range, not durable derived state; "
            "the recurring health pull and the activity refresh are separate scheduled jobs."
        ),
    ),
)
