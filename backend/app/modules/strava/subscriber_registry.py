"""Durable command registration for the Strava module."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry

import modules.strava.subscribers as strava_subscribers


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the Strava command handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    strava_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        strava_subscribers.SYNC_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A sync is a command to re-read the user's Strava gear or to unlink the account, not durable "
            "derived state; the user queues it again if it fails, and activities are a separate ingestion job."
        ),
    ),
)
