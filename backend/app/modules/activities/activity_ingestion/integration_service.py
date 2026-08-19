"""The ingestion surface consumed by provider modules.

A provider (Strava, Garmin) fetches files from its API or an export and hands
them to ingestion. It used to do that by importing ``bulk_entry`` and ``sources``
by path — the right *direction* (a provider depends on activities, never the
reverse) but not a published surface: two internal modules named at the call
site, so nothing distinguished the entry point from the pipeline's plumbing
around it.

This is that surface. Providers import one module and get the entry point plus
the source types they need to describe where a file came from, including the
:class:`BulkImportSource` base a provider export subclasses.
"""

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.background as ingestion_background
import modules.activities.activity_ingestion.bulk_entry as bulk_entry
import modules.activities.activity_ingestion.ingestion_jobs as ingestion_jobs
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.activities.activity_ingestion.sources as ingestion_sources

#: Where a file came from, and the metadata that source carries. Re-exported so a
#: provider names one module rather than reaching for the package internals.
UploadSource = ingestion_sources.UploadSource
GarminSource = ingestion_sources.GarminSource
BulkImportSource = ingestion_sources.BulkImportSource
IngestionSource = ingestion_sources.IngestionSource
build_import_record = ingestion_sources.build_import_record
FetchWindow = provider_registry.FetchWindow


def ingest_activity_file(
    user_id: int,
    file_path: str,
    db: Session,
    *,
    source: ingestion_sources.IngestionSource,
) -> list[activities_schema.Activity] | None:
    """Validate one on-disk activity file and persist the activities it yields.

    The background entry point: it never raises to its caller. A bulk-import
    failure moves the offending file to the import-error directory and returns
    ``None`` so the rest of the batch continues.

    Must be called from a worker thread with no running event loop (a Starlette
    threadpool, the bulk-import executor, or ``asyncio.to_thread``), because the
    file validation inside it runs a private event loop.

    Args:
        user_id: The owner the activities are stored against.
        file_path: Absolute path to the activity file.
        db: Database session.
        source: Where the file came from, and any source-specific metadata.

    Returns:
        The stored activities, or ``None`` when the file could not be parsed or
        persisted.
    """
    return bulk_entry.store_activity_file(user_id, file_path, db, source=source)


def register_activity_provider(name: str, fetch_window: FetchWindow) -> None:
    """Register an external provider's activity-fetch implementation.

    Args:
        name: Stable provider identifier.
        fetch_window: Coroutine that fetches and stores one user window.

    Returns:
        None.
    """
    provider_registry.register(provider_registry.ActivityProvider(name, fetch_window))


def shutdown_background_ingestion(*, wait: bool = False) -> None:
    """Shut down the non-durable ingestion fallback executor.

    Args:
        wait: Whether to wait for running ingestion tasks.

    Returns:
        None.
    """
    ingestion_background.shutdown(wait=wait)


def prune_expired_ingestion_jobs() -> None:
    """Delete ingestion job rows beyond their retention window."""
    ingestion_jobs.prune_expired_ingestion_jobs()
