"""Subscriber registration for retained activity source files."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from jasil.providers import EventBusProvider

import modules.activities.activity_file_storage.scheduled_jobs as activity_file_storage_scheduled_jobs
import modules.activities.activity_file_storage.subscribers as activity_file_storage_subscribers


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register retained-file cleanup subscribers.

    Args:
        events: The event bus to subscribe on.
    """
    activity_file_storage_subscribers.register_activity_file_cleanup_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register retained-file cleanup durable handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    activity_file_storage_subscribers.register_activity_file_cleanup_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        activity_file_storage_subscribers.ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID,
        activity_file_storage_scheduled_jobs.sweep_orphaned_activity_files,
    ),
)
