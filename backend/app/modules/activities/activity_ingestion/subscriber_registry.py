"""Durable command registration for activity ingestion."""

from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry

import modules.activities.activity_ingestion.subscribers as activity_ingestion_subscribers


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register ingestion command handlers.

    Args:
        registry: The durable-handler registry to register on.
    """
    activity_ingestion_subscribers.register_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        activity_ingestion_subscribers.BULK_IMPORT_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A bulk-import batch is a retryable command that resumes from the cursor on its job "
            "row; a job that stops progressing is closed by the stale-job reaper."
        ),
    ),
    DurableSubscriberNet(
        activity_ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Each upload is a retryable command whose terminal result is recorded "
            "on its ingestion job row; the user retries a failed upload."
        ),
    ),
    DurableSubscriberNet(
        activity_ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A refresh is a command to re-read a provider window, not durable "
            "derived state; periodic provider polling is a separate scheduled job."
        ),
    ),
)
