"""Subscriber registration for retained activity source files."""

import modules.activities.activity_file_storage.subscribers as file_subscribers
from infra.jobs.reconciliation import DurableSubscriberNet
from infra.jobs.registry import JobHandlerRegistry
from infra.providers import EventBusProvider


def register_bus_subscribers(events: EventBusProvider) -> None:
    """Register retained-file cleanup subscribers."""
    file_subscribers.register_activity_file_cleanup_subscribers(events)


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register retained-file cleanup durable handlers."""
    file_subscribers.register_activity_file_cleanup_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        file_subscribers.ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Deletion cleanup is an idempotent teardown keyed by activity id. "
            "A missed source-file delete leaves no servable durable state."
        ),
    ),
)
