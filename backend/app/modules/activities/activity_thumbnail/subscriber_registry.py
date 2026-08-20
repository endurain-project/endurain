"""Subscriber registration and reconciliation for activity thumbnails."""

import modules.activities.activity_thumbnail.integration_service as thumbnail_integration
import modules.activities.activity_thumbnail.subscribers as thumbnail_subscribers
from infra.jobs.reconciliation import DurableSubscriberNet
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register thumbnail bus subscribers."""
    thumbnail_subscribers.register_thumbnail_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register thumbnail durable handlers."""
    thumbnail_subscribers.register_thumbnail_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        thumbnail_subscribers.THUMBNAIL_GENERATE_SUBSCRIBER_ID,
        thumbnail_integration.generate_missing_thumbnails,
    ),
    DurableSubscriberNet(
        thumbnail_subscribers.THUMBNAIL_CLEANUP_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Deletion cleanup is an idempotent teardown keyed by activity id. "
            "Once the row is gone, no durable create-derived state remains."
        ),
    ),
    DurableSubscriberNet(
        thumbnail_subscribers.THUMBNAIL_SETTINGS_CHANGED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "This is an explicit admin-triggered re-render command. Durable mode "
            "commits its outbox event atomically; without durable jobs the admin "
            "can repeat the settings update if scheduling fails."
        ),
    ),
)
