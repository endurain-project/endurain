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
            "Teardown, not derived state: the media rows cascade with the activity, "
            "so once the delete commits there is nothing left to reconcile FROM — a "
            "backfill has no row to find the orphan by. This is a bounded leak, not "
            "an absence of one: a dropped cleanup event strands the media blob in "
            "storage for good, and that blob is user-uploaded photo content that "
            "outlives the activity (and, on account deletion, the account). It stays "
            "unreachable — every media URL is signed and expiring — but it is "
            "retained. Closing it needs a storage-side sweep that lists each area and "
            "deletes keys with no owning row; until that exists this is a known "
            "erasure gap, not a harmless one."
        ),
    ),
)
