"""Durable command registration for activity ingestion."""

import modules.activities.activity_ingestion.bulk_import_subscribers as bulk_import_subscribers
import modules.activities.activity_ingestion.ingestion_subscribers as ingestion_subscribers
from infra.jobs.reconciliation import DurableSubscriberNet
from infra.jobs.registry import JobHandlerRegistry


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register ingestion command handlers."""
    bulk_import_subscribers.register_bulk_import_durable_handlers(registry)
    ingestion_subscribers.register_ingestion_durable_handlers(registry)


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        bulk_import_subscribers.BULK_IMPORT_FILE_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Each bulk-import file is itself a retryable command that dead-letters "
            "after exhausting attempts; there is no derived state to backfill."
        ),
    ),
    DurableSubscriberNet(
        ingestion_subscribers.UPLOADED_FILE_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Each upload is a retryable command whose terminal result is recorded "
            "on its ingestion job row; the user retries a failed upload."
        ),
    ),
    DurableSubscriberNet(
        ingestion_subscribers.REFRESH_REQUESTED_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "A refresh is a command to re-read a provider window, not durable "
            "derived state; periodic provider polling is a separate scheduled job."
        ),
    ),
)
