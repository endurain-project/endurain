"""Subscriber registration and reconciliation for activity geocoding."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.activities.activity_geocoding.scheduled_jobs as activity_geocoding_scheduled_jobs
import modules.activities.activity_geocoding.subscribers as activity_geocoding_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register geocoding bus subscribers.

    Args:
        events: The event bus to subscribe on.
    """
    activity_geocoding_subscribers.register_geocoding_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register geocoding durable handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    activity_geocoding_subscribers.register_geocoding_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        activity_geocoding_subscribers.GEOCODING_SUBSCRIBER_ID,
        activity_geocoding_scheduled_jobs.run_missing_location_backfill,
    ),
)
