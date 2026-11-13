"""The ingestion surface consumed by provider modules.

A provider (Strava, Garmin) fetches files from its API or an export and hands
them to ingestion. Providers import this one module and get the entry point plus
the source types they need to describe where a file came from, including the
:class:`BulkImportSource` base a provider export subclasses.
"""

import uuid
from collections.abc import Callable, Collection, Iterable
from datetime import UTC, date, datetime

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from fastapi import Request, Response
from sqlalchemy.orm import Session

import core.job_status as core_job_status
import core.location as core_location
import core.logger as core_logger
import core.sync_runner as core_sync_runner
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.background as activity_ingestion_background
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.crud as activity_ingestion_crud
import modules.activities.activity_ingestion.provider_entry_service as activity_ingestion_provider_entry_service
import modules.activities.activity_ingestion.provider_registry as activity_ingestion_provider_registry
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.activities.activity_ingestion.service as activity_ingestion_service
import modules.activities.activity_ingestion.window_service as activity_ingestion_window_service
import modules.users.users.integration_service as users_integration

#: Where a file came from, and the metadata that source carries. Re-exported so a
#: provider names one module rather than reaching for the package internals.
UploadSource = activity_ingestion_contracts.UploadSource
GarminSource = activity_ingestion_contracts.GarminSource
BulkImportSource = activity_ingestion_contracts.BulkImportSource
BulkImportFormat = activity_ingestion_contracts.BulkImportFormat
ArchiveMemberReader = activity_ingestion_contracts.ArchiveMemberReader
IngestionSource = activity_ingestion_contracts.IngestionSource
WindowStoppedError = activity_ingestion_contracts.WindowStoppedError
build_import_record = activity_ingestion_contracts.build_import_record

logger = core_logger.get_logger(__name__)


def ingest_activity_file(
    user_id: uuid.UUID,
    file_path: str,
    db: Session,
    *,
    source: activity_ingestion_contracts.IngestionSource,
) -> list[activity_schema.ActivityRead] | None:
    """Validate one on-disk activity file and persist the activities it yields.

    The background entry point: a file the pipeline refuses is logged and
    returned as ``None`` so the provider's sync moves on to the next activity. Any
    other failure (a database or storage outage, a bug) is raised, for the
    provider's window to record and retry.

    Must be called from a worker thread with no running event loop (a Starlette
    threadpool, the bulk-import executor, or ``asyncio.to_thread``), because the
    file validation inside it runs a private event loop.

    Args:
        user_id: The owner the activities are stored against.
        file_path: Absolute path to the activity file.
        db: Database session.
        source: Where the file came from, and any source-specific metadata.

    Returns:
        The stored activities, or ``None`` when the file was refused as
        unparseable or invalid.

    Raises:
        Exception: Any failure that is not a refusal of the file.
    """
    return activity_ingestion_provider_entry_service.store_activity_file(
        user_id, file_path, platform_runtime.get_active_platform().storage, db, source=source
    )


def register_activity_provider(
    name: str,
    fetch_window: activity_ingestion_contracts.FetchWindow,
    linked_user_ids: activity_ingestion_contracts.LinkedUserIds,
) -> None:
    """Register an external provider's activity-fetch implementation.

    Args:
        name: Stable provider identifier.
        fetch_window: Fetches and stores one user's window; synchronous and
            session-less, opening its own short sessions.
        linked_user_ids: Pages through the users who have linked the provider.
    """
    activity_ingestion_provider_registry.register(
        activity_ingestion_provider_registry.ActivityProvider(name, fetch_window, linked_user_ids)
    )


def run_provider_window[ItemT, ResultT](
    items: Iterable[ItemT],
    process: Callable[[ItemT], ResultT],
    *,
    provider: str,
    user_id: uuid.UUID,
    describe: Callable[[ItemT], dict[str, object]],
    propagate: tuple[type[BaseException], ...] = (),
) -> list[ResultT]:
    """Process each activity of a provider's window, raising the first failure once the window is done.

    An activity that cannot be processed is logged and skipped so the rest of the window is stored; the
    refresh job then fails and is retried, resuming past what is already stored.

    Args:
        items: The provider's activities for the window.
        process: Handles one activity and returns what it produced. It may raise ``WindowStoppedError`` to end
            the window early.
        provider: The provider's name, for the log.
        user_id: The user whose window it is, for the log.
        describe: Names an activity for the log, such as its provider id.
        propagate: Failures that end the window at once and are raised as they are.

    Returns:
        What ``process`` returned for each activity it handled.

    Raises:
        BaseException: Whatever ``propagate`` names, as soon as it is raised.
        Exception: The first failure of an activity, after the rest of the window was processed.
    """
    return activity_ingestion_window_service.run_window(
        items, process, provider=provider, user_id=user_id, describe=describe, propagate=propagate
    )


def request_range_sync(
    provider: str,
    user_id: uuid.UUID,
    start_date: date,
    end_date: date,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a sync of one provider over a whole-day range and return its handle.

    The provider's own "retrieve activities" endpoints use this so a long date range runs as a job
    rather than on an API worker thread. The range is validated against the user's local today and
    the shared length cap.

    Args:
        provider: The registered provider name.
        user_id: The user whose account to sync.
        start_date: First day of the range.
        end_date: Last day of the range, inclusive.
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        The accepted refresh job.

    Raises:
        InvalidInputError: When ``end_date`` is in the future or the
            range is longer than ``MAX_ACTIVITIES_RANGE_DAYS``.
    """
    core_sync_runner.validate_range(
        start_date,
        end_date,
        core_sync_runner.MAX_ACTIVITIES_RANGE_DAYS,
        users_integration.local_today(user_id, db),
    )
    job = activity_ingestion_service.accept_refresh(
        user_id,
        storage,
        db,
        provider=provider,
        window_start=datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        window_end=datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
    )
    logger.info("Provider activities queued", extra=core_logger.context(user_id=user_id, provider=provider))
    return job


def register_bulk_import_format(bulk_format: activity_ingestion_contracts.BulkImportFormat) -> None:
    """Register how a provider's bulk-import archive is laid out and interpreted.

    Args:
        bulk_format: The format; its ``name`` is the ``source`` clients select.
    """
    activity_ingestion_provider_registry.register_bulk_format(bulk_format)


def shutdown_background_ingestion(*, wait: bool = False) -> None:
    """Shut down the non-durable ingestion fallback executor.

    Args:
        wait: Whether to wait for running ingestion tasks.
    """
    activity_ingestion_background.shutdown(wait=wait)


def delete_bulk_import_errors(user_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
    """Delete a user's failed bulk-import files, leaving the retention sweep to catch them if storage fails.

    Runs after the account deletion is committed, so an unavailable storage backend is logged
    rather than raised.

    Args:
        user_id: The user whose failed bulk-import files to remove.
        storage: The platform storage provider.
    """
    try:
        storage.delete_prefix(
            activity_ingestion_constants.BULK_IMPORT_ERROR_STORAGE_AREA,
            activity_ingestion_constants.bulk_import_error_prefix(user_id),
        )
    except platform_providers.StorageBackendUnavailableError as err:
        logger.warning(
            "Could not delete a user's failed bulk-import files",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )


def set_job_location(
    response: Response, request: Request, job: activity_ingestion_schema.ActivityIngestionJobRead
) -> None:
    """Name the ingestion job's read route and the wait before the first poll on a ``202``.

    Args:
        response: The response of the route that accepted the job.
        request: The request, which resolves the job route's path.
        job: The accepted job.
    """
    kind = activity_ingestion_constants.IngestionJobKind.from_job_kind(job.kind)
    core_location.set_job_location(response, request, job.id, activity_ingestion_constants.JOB_POLL_SECONDS[kind])


def read_job(job_id: str, user_id: uuid.UUID, db: Session) -> activity_ingestion_schema.ActivityIngestionJobRead | None:
    """Return one of a user's ingestion jobs.

    Args:
        job_id: The job identifier.
        user_id: The user who must own the job.
        db: Database session.

    Returns:
        The job, or ``None`` when it does not exist or belongs to someone else.
    """
    return activity_ingestion_crud.get_ingestion_job(job_id, user_id, db)


def list_jobs(
    user_id: uuid.UUID,
    db: Session,
    *,
    kinds: Collection[str],
    status: core_job_status.JobState | None,
    before: tuple[datetime, str] | None,
    limit: int,
) -> list[activity_ingestion_schema.ActivityIngestionJobRead]:
    """List a user's ingestion jobs, newest first.

    Args:
        user_id: The job owner.
        db: Database session.
        kinds: The job kinds to list, as clients name them (``activity_upload``).
        status: Only jobs in this state, or ``None`` for any.
        before: Only jobs strictly older than this ``(created_at, id)`` position, or ``None`` from the newest.
        limit: The most jobs to return.

    Returns:
        The jobs, at most ``limit``.
    """
    return activity_ingestion_service.list_jobs(user_id, db, kinds=kinds, status=status, before=before, limit=limit)
