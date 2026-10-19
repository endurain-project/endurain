"""Subscriber registration and reconciliation for activity thumbnails."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.activities.activity_thumbnail.scheduled_jobs as activity_thumbnail_scheduled_jobs
import modules.activities.activity_thumbnail.subscribers as activity_thumbnail_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register thumbnail bus subscribers.

    Args:
        events: The event bus to subscribe on.
    """
    activity_thumbnail_subscribers.register_thumbnail_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register thumbnail durable handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    activity_thumbnail_subscribers.register_thumbnail_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        activity_thumbnail_subscribers.THUMBNAIL_GENERATE_SUBSCRIBER_ID,
        activity_thumbnail_scheduled_jobs.generate_missing_thumbnails,
    ),
    DurableSubscriberNet(
        activity_thumbnail_subscribers.THUMBNAIL_CLEANUP_SUBSCRIBER_ID,
        activity_thumbnail_scheduled_jobs.sweep_orphaned_thumbnails,
    ),
    DurableSubscriberNet(
        activity_thumbnail_subscribers.THUMBNAIL_SETTINGS_CHANGED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "This is an explicit admin-triggered re-render command. Durable mode "
            "commits its outbox event atomically; without durable jobs the admin "
            "can repeat the settings update if scheduling fails."
        ),
    ),
)
