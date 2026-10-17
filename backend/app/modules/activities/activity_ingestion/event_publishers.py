"""Publish the activity-ingestion domain events through the platform publish facade.

Each function knows its channel and correlation metadata and delegates envelope
assembly and the transactional outbox to :mod:`jasil.publisher`. Every channel
here is durable-delivery only: the event **is** the work, so each is published
with the caller's commit and a staging failure propagates rather than being
swallowed.
"""

from collections.abc import Callable

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.activities.activity_ingestion.events as activity_ingestion_events


def publish_file_uploaded(job_id: str, user_id: int, db: Session, *, commit: Callable[[], None]) -> None:
    """Publish ``activity.file_uploaded`` so a durable worker imports the staged upload.

    Staged in the transactional outbox on ``db`` and committed with the job row,
    then relayed into a retryable ``processing_jobs`` row.

    Args:
        job_id: The ``activity_ingestion_jobs`` row to process.
        user_id: The uploading user's ID.
        db: The session the job row was created on.
        commit: Zero-arg commit callable that ends the caller's transaction.
    """
    payload = activity_ingestion_events.UploadedFilePayload(job_id=job_id)
    platform_publisher.publish_committing(
        activity_ingestion_events.ACTIVITY_FILE_UPLOADED,
        payload.model_dump(),
        source="api:upload",
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_refresh_requested(job_id: str, user_id: int, db: Session, *, commit: Callable[[], None]) -> None:
    """Publish ``activity.refresh_requested`` so a durable worker syncs the providers.

    Args:
        job_id: The ``activity_ingestion_jobs`` row to process.
        user_id: The requesting user's ID.
        db: The session the job row was created on.
        commit: Zero-arg commit callable that ends the caller's transaction.
    """
    payload = activity_ingestion_events.RefreshRequestedPayload(job_id=job_id)
    platform_publisher.publish_committing(
        activity_ingestion_events.ACTIVITY_REFRESH_REQUESTED,
        payload.model_dump(),
        source="api:refresh",
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )


def publish_refresh_requests(
    jobs: list[tuple[str, int]],
    db: Session,
    *,
    commit: Callable[[], None],
) -> None:
    """Publish one ``activity.refresh_requested`` per refresh job in one transaction.

    Used by the scheduled fan-out, which creates a job per linked user: the whole
    batch is staged in the caller's transaction and committed once, instead of a
    commit per user.

    Args:
        jobs: ``(job id, owning user id)`` per refresh job.
        db: The session the job rows were created on.
        commit: Zero-arg commit callable that ends the caller's transaction.
    """
    owner_of = dict(jobs)
    platform_publisher.publish_many_committing(
        activity_ingestion_events.ACTIVITY_REFRESH_REQUESTED,
        [activity_ingestion_events.RefreshRequestedPayload(job_id=job_id).model_dump() for job_id, _ in jobs],
        source="scheduler:provider_refresh",
        metadata_for=lambda payload: {core_event_metadata.META_USER_ID: owner_of[payload["job_id"]]},
        db=db,
        commit=commit,
        schema_version=activity_ingestion_events.RefreshRequestedPayload.SCHEMA_VERSION,
    )


def publish_bulk_import_continue(job_id: str, user_id: int, db: Session, *, commit: Callable[[], None]) -> None:
    """Publish ``activity.bulk_import_continue`` so a worker runs the next batch.

    Staged in the transactional outbox on ``db`` and committed with whatever the
    caller staged — the archive record when an import is accepted, the resume
    point when a batch ends — so a crash cannot leave progress without its
    continuation, or a continuation without its progress.

    Args:
        job_id: The ``activity_ingestion_jobs`` row to continue.
        user_id: The importing user's ID.
        db: The session the job row was staged on.
        commit: Zero-arg commit callable that ends the caller's transaction.
    """
    payload = activity_ingestion_events.BulkImportContinuePayload(job_id=job_id)
    platform_publisher.publish_committing(
        activity_ingestion_events.ACTIVITY_BULK_IMPORT_CONTINUE,
        payload.model_dump(),
        source="api:bulk_import",
        db=db,
        commit=commit,
        metadata={core_event_metadata.META_USER_ID: user_id},
        schema_version=payload.SCHEMA_VERSION,
    )
