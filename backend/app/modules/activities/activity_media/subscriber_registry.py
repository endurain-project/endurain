"""Subscriber registration for activity media cleanup."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.activities.activity_media.scheduled_jobs as activity_media_scheduled_jobs
import modules.activities.activity_media.subscribers as activity_media_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register media cleanup subscribers.

    Args:
        events: The event bus to subscribe on.
    """
    activity_media_subscribers.register_activity_media_cleanup_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register media cleanup durable handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    activity_media_subscribers.register_activity_media_cleanup_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        activity_media_subscribers.ACTIVITY_MEDIA_CLEANUP_SUBSCRIBER_ID,
        activity_media_scheduled_jobs.sweep_orphaned_media,
    ),
)
