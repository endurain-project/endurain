"""Subscriber registration and reconciliation for activity thumbnails."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.activities.activity_thumbnail.integration_service as thumbnail_integration
import modules.activities.activity_thumbnail.subscribers as thumbnail_subscribers


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
            "Teardown, not derived state, and the direction matters: the generate "
            "net above reconciles FROM the activity row, so it can only ever find "
            "activities that still exist. A dropped cleanup event leaves a thumbnail "
            "blob whose activity is gone, which no row-driven backfill can reach. The "
            "leak is bounded and the blob is unreachable (its URL is signed and "
            "expiring), but it is derived from user GPS data and it outlives the "
            "deletion. Closing it needs a storage-side sweep over the thumbnail area; "
            "until that exists this is a known erasure gap."
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
