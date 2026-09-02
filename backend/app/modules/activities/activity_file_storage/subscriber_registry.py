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
            "Teardown, not derived state: once the activity row is gone no backfill "
            "can discover the retained source file, because the row was the only "
            "thing naming it. A dropped cleanup event therefore keeps the uploaded "
            "FIT/GPX/TCX file — the athlete's original recording — in storage "
            "permanently. It is unservable without an activity to serve it under, but "
            "it is retained past the deletion that was meant to remove it. Closing it "
            "needs a storage-side sweep keyed on the absence of an owning row; until "
            "that exists this is a known erasure gap."
        ),
    ),
)
