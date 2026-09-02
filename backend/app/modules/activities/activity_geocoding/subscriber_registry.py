"""Subscriber registration and reconciliation for activity geocoding."""

import modules.activities.activity_geocoding.integration_service as geocoding_integration
import modules.activities.activity_geocoding.subscribers as geocoding_subscribers
from infra.jobs.reconciliation import DurableSubscriberNet
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register geocoding bus subscribers."""
    geocoding_subscribers.register_geocoding_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register geocoding durable handlers."""
    geocoding_subscribers.register_geocoding_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        geocoding_subscribers.GEOCODING_SUBSCRIBER_ID,
        geocoding_integration.run_missing_location_backfill,
    ),
)
