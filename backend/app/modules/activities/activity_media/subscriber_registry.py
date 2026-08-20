"""Subscriber registration for activity media cleanup."""

import modules.activities.activity_media.subscribers as media_subscribers
from infra.jobs.reconciliation import DurableSubscriberNet
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register media cleanup subscribers."""
    media_subscribers.register_activity_media_cleanup_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register media cleanup durable handlers."""
    media_subscribers.register_activity_media_cleanup_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        media_subscribers.ACTIVITY_MEDIA_CLEANUP_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Deletion cleanup is idempotent and the media rows cascade with the "
            "activity, so no durable record remains from which to reconcile it."
        ),
    ),
)
