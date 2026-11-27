"""Recompute every activity stored under an older file analysis from its retained file, as a resumable job.

The data migration the ``migrations`` table tracks as row 15. A boot handler would hold startup, and every replica
waiting for the migration lock, for as long as the walk takes, so startup only *requests* the walk: with durable jobs
(``JOBS_ENABLED``) it publishes a request a worker runs in bounded passes, otherwise it hands the walk to a pool of
its own, so the API serves meanwhile.

The walk lists the activities below ``ANALYSIS_VERSION`` and settles them one at a time, each in its own
transaction: a reprocessed activity is stamped by the reprocess itself, any other (no retained file, no matching
session, an unreadable file, an unexpected failure) is stamped here so it is not listed again. The migration is marked
executed only when nothing is left below the version, so a walk that stops, in a pass or in a crash, resumes from what
is left. A pass runs under a distributed lock, so two never run at once.
"""

import time
import uuid
from datetime import UTC

import jasil.event_versioning as platform_event_versioning
import jasil.orm as jasil_orm
import jasil.providers as platform_providers
import jasil.publisher as platform_publisher
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs import ContinueJob
from jasil.jobs.reconciliation import DurableSubscriberNet
from jasil.jobs.registry import JobHandlerRegistry
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.job_queues as core_job_queues
import core.local_pool as core_local_pool
import core.logger as core_logger
import migrations.crud as migrations_crud
import migrations.events as migrations_events
import migrations.service as migrations_service
import modules.activities.activity_ingestion.migration_service as activity_ingestion_migration

logger = core_logger.get_logger(__name__)

#: The ``migrations`` row this job completes; the Alembic revision that adds the row names the same id.
MIGRATION_ID = 15
#: Held by a pass for as long as it runs, so two passes, on two replicas or on a worker and the pool, never overlap.
LOCK_NAME = "activity_reprocess"
REPROCESS_SUBSCRIBER_ID = "migrations.activity_reprocess"

#: Activities listed at a time.
_BATCH_SIZE = 50

# One walk at a time is all the lock allows, so the pool holds one job; a request while it is held is dropped.
_pool = core_local_pool.BoundedPool("activity-reprocess", workers=1, max_pending=1)


def shutdown_pool() -> None:
    """Stop the pool without waiting; a walk it was running resumes at the next start."""
    _pool.shutdown()


def _is_outage(err: Exception) -> bool:
    """Return whether an error means a dependency is out of reach, which says nothing about the activity.

    Storage refusals count too: a misconfigured store would otherwise mark every activity as visited without
    reprocessing it.

    Args:
        err: What reprocessing one activity raised.

    Returns:
        True for storage, the database or a service that is unavailable.
    """
    return isinstance(
        err, core_exceptions.ServiceUnavailableError | platform_providers.StorageBackendUnavailableError
    ) or jasil_orm.is_database_unavailable(err)


def _settle(activity_id: uuid.UUID, storage: platform_providers.StorageProvider) -> bool:
    """Reprocess one activity, and stamp it when the reprocess did not.

    Args:
        activity_id: The activity to settle.
        storage: The blob-storage provider the activity's file is retained in.

    Returns:
        True when the activity was reprocessed.

    Raises:
        Exception: An outage of storage, the database or a service, so the pass is retried with the activity unstamped.
    """
    try:
        outcome = activity_ingestion_migration.reprocess_activity(activity_id, storage)
    except Exception as err:
        if _is_outage(err):
            raise
        logger.error(
            "Could not reprocess an activity; it keeps its values and is not retried",
            exc_info=err,
            extra=core_logger.context(activity_id=activity_id),
        )
        outcome = None
    # Stamped whatever the outcome, so an activity is never listed again and the walk always ends; a no-op on one
    # the reprocess already stamped.
    activity_ingestion_migration.mark_reprocess_visited(activity_id)
    return outcome is activity_ingestion_migration.ReprocessOutcome.REPROCESSED


def _mark_executed() -> None:
    """Record the migration as executed, in a session of its own."""
    with core_database.SessionLocal() as db:
        migrations_service.mark_executed(MIGRATION_ID, db)


def run_batch(storage: platform_providers.StorageProvider, time_budget: float | None) -> bool:
    """Reprocess the activities below the current analysis version, and complete the migration when none are left.

    Lists the next ids and settles them one by one until none are left or the time budget is spent. At least one
    activity is settled per call, so every pass makes progress. Nothing here holds a database session across a
    storage read: each step opens and closes its own.

    Args:
        storage: The blob-storage provider the activities' files are retained in.
        time_budget: Seconds after which to stop, or ``None`` to run to the end.

    Returns:
        True when activities may be left and the caller must run it again; False when none are, and the migration is
        executed.

    Raises:
        Exception: An outage of storage, the database or a service; the activity it hit is left unstamped.
    """
    deadline = None if time_budget is None else time.monotonic() + time_budget
    reprocessed = skipped = 0
    while True:
        activity_ids = activity_ingestion_migration.list_activities_to_reprocess(_BATCH_SIZE)
        if not activity_ids:
            _mark_executed()
            logger.info(
                "Activity reprocess finished",
                extra=core_logger.context(reprocessed=reprocessed, skipped=skipped, migration=MIGRATION_ID),
            )
            return False
        for activity_id in activity_ids:
            if _settle(activity_id, storage):
                reprocessed += 1
            else:
                skipped += 1
            if deadline is not None and time.monotonic() >= deadline:
                logger.debug(
                    "Activity reprocess pass ended with activities left",
                    extra=core_logger.context(reprocessed=reprocessed, skipped=skipped),
                )
                return True


def run_pass(
    storage: platform_providers.StorageProvider, lock: platform_providers.LockProvider, time_budget: float | None
) -> bool:
    """Run :func:`run_batch` while holding the job's lock; a pass that finds it held does nothing.

    Args:
        storage: The blob-storage provider the activities' files are retained in.
        lock: The coordination lock provider.
        time_budget: Seconds after which to stop, or ``None`` to run to the end.

    Returns:
        True when the caller must run it again; False when it finished, or when another pass holds the lock and
        walks the activities instead.
    """
    with lock.try_acquire(LOCK_NAME) as acquired:
        if not acquired:
            logger.debug("Activity reprocess: another pass holds the lock")
            return False
        return run_batch(storage, time_budget)


def _is_pending(db: Session) -> bool:
    """Return whether the migration has not been marked executed.

    Args:
        db: Database session.

    Returns:
        True while its ``migrations`` row is pending.
    """
    return any(migration.id == MIGRATION_ID for migration in migrations_crud.get_migrations_not_executed(db))


def request_reprocess() -> None:
    """Ask for the reprocess to run while the migration is pending, without running any of it here.

    A startup task, so it must return at once. With durable jobs it publishes one request named after the hour it
    is made in, so every replica starting within the hour queues a single pass between them. Without them it hands
    the walk to the module's pool; a walk already queued or running there makes the request redundant.
    """
    platform = platform_runtime.get_active_platform()
    with core_database.SessionLocal() as db:
        if not _is_pending(db):
            logger.debug("Activity reprocess: the migration is already executed")
            return
        if core_config.settings.JOBS_ENABLED:
            payload = migrations_events.ActivityReprocessRequestedPayload()
            platform_publisher.publish_committing(
                migrations_events.ACTIVITY_REPROCESS_REQUESTED,
                payload.model_dump(mode="json"),
                source="startup:activity_reprocess",
                db=db,
                commit=db.commit,
                schema_version=payload.SCHEMA_VERSION,
                event_id=(
                    f"activity-reprocess-v{activity_ingestion_migration.ANALYSIS_VERSION}-"
                    f"{platform.clock.now().astimezone(UTC):%Y%m%d%H}"
                ),
            )
            return
    try:
        _pool.submit(run_pass, platform.storage, platform.lock, None)
    except core_local_pool.PoolFullError:
        logger.debug("Activity reprocess: a walk is already queued or running")


def handle_reprocess_requested(event: Event) -> None:
    """Durable handler: run one bounded pass of the reprocess; an exception makes the worker retry it.

    A pass that spends its budget with activities left ends with ``ContinueJob``, so the same job walks the rest.

    Args:
        event: The ``migrations.activity_reprocess_requested`` event.

    Raises:
        ContinueJob: When activities may be left.
    """
    platform_event_versioning.parse_payload(migrations_events.ActivityReprocessRequestedPayload, event)
    platform = platform_runtime.get_active_platform()
    if run_pass(platform.storage, platform.lock, core_job_queues.durable_pass_seconds()):
        raise ContinueJob(reason="activity reprocess pass finished with activities left")


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the reprocess as a durable job subscriber on the background queue.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        migrations_events.ACTIVITY_REPROCESS_REQUESTED,
        REPROCESS_SUBSCRIBER_ID,
        handle_reprocess_requested,
        queue=core_job_queues.BACKGROUND,
    )


DURABLE_SUBSCRIBER_NETS: tuple[DurableSubscriberNet, ...] = (
    DurableSubscriberNet(
        REPROCESS_SUBSCRIBER_ID,
        None,
        exempt_reason=(
            "Every API start requests the reprocess again until its migration is marked executed, so a lost or "
            "dead-lettered request is replaced at the next start."
        ),
    ),
)
