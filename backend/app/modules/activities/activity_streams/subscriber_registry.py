"""Subscriber registration and reconciliation for activity streams."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.activities.activity_streams.integration_service as streams_integration
import modules.activities.activity_streams.subscribers as stream_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register stream bus subscribers."""
    stream_subscribers.register_hr_zone_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register stream durable handlers."""
    stream_subscribers.register_hr_zone_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        stream_subscribers.HR_ZONE_SUBSCRIBER_ID,
        streams_integration.run_missing_hr_zone_backfill,
    ),
)
