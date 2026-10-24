"""Queue Garmin Connect activity, gear and health syncs so they never run on an API thread.

On the durable profile (``JOBS_ENABLED``) the request stages a ``garmin.sync_requested`` event
and a worker runs it, surviving a restart. Otherwise the same body runs on a small in-process
pool that is not the request threadpool. Either way a gear or health sync is recorded in the
shared sync state, which the client polls and which stops a user queueing the same sync twice.
"""

import contextvars
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.garmin.constants as garmin_constants
import modules.garmin.event_publishers as garmin_event_publishers
import modules.garmin.events as garmin_events
import modules.garmin.gear_service as garmin_gear_service
import modules.garmin.health_service as garmin_health_service
import modules.garmin.schema as garmin_schema
import modules.garmin.service as garmin_service
import modules.garmin.sync_state_store as garmin_sync_state_store
import modules.users.users.integration_service as users_integration

logger = core_logger.get_logger(__name__)

# Small on purpose: syncs are Garmin round trips and compete with the request threads.
_MAX_WORKERS = 2
_SYNC_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="garmin-sync")
_local_slots = threading.BoundedSemaphore(garmin_constants.MAX_PENDING_LOCAL_SYNCS)

_USERS_PAGE_SIZE = 100


class LocalPoolFullError(core_exceptions.ServiceUnavailableError):
    """Raised when the in-process pool stays full for the whole time a caller is willing to wait."""


def shutdown_sync_executor(*, wait: bool = False) -> None:
    """Stop accepting syncs and release the pool threads.

    Args:
        wait: Whether to wait for syncs still running.
    """
    _SYNC_EXECUTOR.shutdown(wait=wait, cancel_futures=True)


def _validate_range(start_date: date, end_date: date, max_days: int | None = None) -> None:
    """Refuse a reversed date range, or one longer than ``max_days``.

    Args:
        start_date: First day of the range.
        end_date: Last day of the range.
        max_days: Longest range allowed, or ``None`` for no cap.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date`` or the range is too long.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")
    if max_days is not None and end_date - start_date >= timedelta(days=max_days):
        raise core_exceptions.InvalidInputError(f"The date range must not exceed {max_days} days")


def run_sync(payload: garmin_events.SyncRequestedPayload, states: garmin_sync_state_store.GarminSyncStateStore) -> None:
    """Run one queued sync and record its outcome. Blocking; call it from a worker, never a request.

    A sync that could not run because the account is not linked or Garmin Connect rejected its
    token is recorded as failed and not raised: a retry would meet the same answer.

    A sync that raised is retried by a durable worker, so it stays ``QUEUED`` with its claim held:
    releasing the claim would let a second sync start beside the retry, and the claim runs out on
    its own if the retries are exhausted. Without a worker nothing retries it, so it is ``FAILED``
    and the claim is released.

    Args:
        payload: What to sync.
        states: Shared store of the sync's state.

    Raises:
        Exception: Whatever the sync raised, after recording its state, so a durable worker retries it.
    """
    states.set_status(payload.user_id, payload.kind, garmin_constants.SyncStatus.RUNNING)
    synced = False
    try:
        if payload.kind == garmin_constants.SyncKind.GEAR:
            synced = garmin_gear_service.get_user_gear(payload.user_id)
        elif payload.start_date is not None and payload.end_date is not None:
            synced = garmin_health_service.sync_health_for_dates(payload.start_date, payload.end_date, payload.user_id)
    except Exception:
        retried = core_config.settings.JOBS_ENABLED
        states.set_status(
            payload.user_id,
            payload.kind,
            garmin_constants.SyncStatus.QUEUED if retried else garmin_constants.SyncStatus.FAILED,
        )
        raise
    outcome = garmin_constants.SyncStatus.COMPLETED if synced else garmin_constants.SyncStatus.FAILED
    states.set_status(payload.user_id, payload.kind, outcome)


def _finish_local(future: Future) -> None:
    """Give a local pool slot back and log an exception raised by a sync on the pool."""
    _local_slots.release()
    exc = future.exception()
    if exc is not None:
        logger.error("Garmin Connect sync failed", exc_info=exc)


def _submit_local(
    payload: garmin_events.SyncRequestedPayload,
    states: garmin_sync_state_store.GarminSyncStateStore,
    wait_seconds: float,
) -> None:
    """Run a sync on the in-process pool, refusing it when the pool stays at its limit.

    Args:
        payload: What to sync.
        states: Shared store of the sync's state.
        wait_seconds: How long to wait for a slot when the pool is full; ``0`` refuses at once.

    Raises:
        LocalPoolFullError: When the pool still holds ``MAX_PENDING_LOCAL_SYNCS`` syncs after the wait.
    """
    if not _local_slots.acquire(timeout=wait_seconds):
        raise LocalPoolFullError("Too many Garmin Connect syncs in progress; try again shortly")
    try:
        future = _SYNC_EXECUTOR.submit(contextvars.copy_context().run, run_sync, payload, states)
    except BaseException:
        _local_slots.release()
        raise
    future.add_done_callback(_finish_local)
    logger.info(
        "Garmin Connect sync queued on the in-process pool",
        extra=core_logger.context(user_id=payload.user_id, kind=payload.kind),
    )


def _queue(
    user_id: int,
    kind: garmin_constants.SyncKind,
    start_date: date | None,
    end_date: date | None,
    states: garmin_sync_state_store.GarminSyncStateStore,
    db: Session,
    *,
    source: str = garmin_constants.SYNC_SOURCE_API,
    wait_seconds: float = 0,
) -> garmin_schema.GarminSyncStatus:
    """Hand a sync to a worker, or to the in-process pool without durable jobs.

    Args:
        user_id: The user to sync.
        kind: What to pull.
        start_date: First day of the range, for a health sync.
        end_date: Last day of the range, for a health sync.
        states: Shared store of the sync's state.
        db: Database session.
        source: Who asked for the sync, as recorded on the event.
        wait_seconds: How long to wait for a pool slot when the pool is full.

    Returns:
        The sync's initial status.

    Raises:
        ConflictError: When a sync of this kind is already pending for the user.
        LocalPoolFullError: When the in-process pool is still full after the wait.
    """
    if not states.begin(user_id, kind):
        raise core_exceptions.ConflictError(f"A Garmin Connect {kind.value} sync is already in progress")
    try:
        if core_config.settings.JOBS_ENABLED:
            garmin_event_publishers.publish_sync_requested(
                user_id, kind, start_date, end_date, db, commit=db.commit, source=source
            )
            logger.info(
                "Garmin Connect sync queued for a worker", extra=core_logger.context(user_id=user_id, kind=kind)
            )
        else:
            payload = garmin_events.SyncRequestedPayload(
                user_id=user_id, kind=kind, start_date=start_date, end_date=end_date
            )
            _submit_local(payload, states, wait_seconds)
    except BaseException:
        # The sync never started, so nothing else would finish its claim.
        states.set_status(user_id, kind, garmin_constants.SyncStatus.FAILED)
        raise
    return garmin_schema.GarminSyncStatus(kind=kind, status=garmin_constants.SyncStatus.QUEUED)


def request_gear_sync(
    user_id: int, states: garmin_sync_state_store.GarminSyncStateStore, db: Session
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect gear.

    Args:
        user_id: The user to sync.
        states: Shared store of the sync's state.
        db: Database session.

    Returns:
        The sync's initial status.
    """
    return _queue(user_id, garmin_constants.SyncKind.GEAR, None, None, states, db)


def request_health_sync(
    user_id: int,
    start_date: date,
    end_date: date,
    states: garmin_sync_state_store.GarminSyncStateStore,
    db: Session,
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect health data for a range of days.

    Args:
        user_id: The user to sync.
        start_date: First day of the range.
        end_date: Last day of the range.
        states: Shared store of the sync's state.
        db: Database session.

    Returns:
        The sync's initial status.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date`` or the range is longer than
            ``MAX_HEALTH_RANGE_DAYS``.
    """
    _validate_range(start_date, end_date, garmin_constants.MAX_HEALTH_RANGE_DAYS)
    return _queue(user_id, garmin_constants.SyncKind.HEALTH, start_date, end_date, states, db)


def get_sync_status(
    user_id: int, kind: garmin_constants.SyncKind, states: garmin_sync_state_store.GarminSyncStateStore
) -> garmin_schema.GarminSyncStatus:
    """Report where a user's gear or health sync is.

    Args:
        user_id: The user being synced.
        kind: What the sync pulls.
        states: Shared store of the sync's state.

    Returns:
        The sync's status.

    Raises:
        NotFoundError: When no sync is recorded or it has expired.
    """
    state = states.get(user_id, kind)
    if state is None:
        raise core_exceptions.NotFoundError(f"No Garmin Connect {kind.value} sync recorded")
    return garmin_schema.GarminSyncStatus(kind=kind, status=state.status)


def request_activities_sync(
    user_id: int,
    start_date: date,
    end_date: date,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Garmin Connect sync of an explicit date range.

    The range is fetched by a background job, never on the request or an API worker thread. It is
    not capped: a first sync may reach back years.

    Args:
        user_id: The user to sync.
        start_date: First day of the range.
        end_date: Last day of the range.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The queued job's handle.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date``.
    """
    _validate_range(start_date, end_date)

    job = activity_ingestion_integration.request_provider_sync(
        user_id,
        garmin_constants.PROVIDER_NAME,
        datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
        storage,
        db,
    )
    logger.info(
        "Garmin Connect activities queued",
        extra=core_logger.context(user_id=user_id),
    )
    return job


def _sync_recent_health_for_user(user_id: int, states: garmin_sync_state_store.GarminSyncStateStore) -> None:
    """Queue one user's recent health data for a worker, or for the in-process pool without durable jobs.

    The window is yesterday and today in the user's own timezone, as Garmin Connect dates its
    records by the user's day. A user whose health sync is still pending is skipped: the window
    overlaps the next run, so nothing is lost.

    Args:
        user_id: The user to sync.
        states: Shared store of the sync's state.

    Raises:
        LocalPoolFullError: When the in-process pool stayed full for the whole wait.
    """
    with core_database.SessionLocal() as db:
        end_date = users_integration.local_today(user_id, db)
        try:
            _queue(
                user_id,
                garmin_constants.SyncKind.HEALTH,
                end_date - timedelta(days=1),
                end_date,
                states,
                db,
                source=garmin_constants.SYNC_SOURCE_SCHEDULER,
                wait_seconds=garmin_constants.SCHEDULED_SLOT_WAIT_SECONDS,
            )
        except core_exceptions.ConflictError:
            logger.debug("Garmin Connect health sync already pending", extra=core_logger.context(user_id=user_id))


def sync_recent_health(states: garmin_sync_state_store.GarminSyncStateStore) -> None:
    """Sync the last day of Garmin Connect health stats for every linked user.

    Each user's sync is queued, for a worker with durable jobs or for the in-process pool without
    them, so users are isolated and never run on this thread. Linked users are read a page at a
    time in short sessions, and one user failing does not stop the rest. Without durable jobs a
    full pool is waited on; if it stays full the pass stops, and the next run starts over.

    Args:
        states: Shared store of the syncs' state.
    """
    after_id = 0
    while True:
        try:
            user_ids = garmin_service.linked_user_ids(after_id, _USERS_PAGE_SIZE)
        except Exception as err:
            logger.error("Error getting the users linked to Garmin Connect", exc_info=err)
            return
        if not user_ids:
            return
        for user_id in user_ids:
            try:
                _sync_recent_health_for_user(user_id, states)
            except LocalPoolFullError:
                logger.warning(
                    "Garmin Connect health pull stopped: the in-process pool stayed full",
                    extra=core_logger.context(user_id=user_id),
                )
                return
            except Exception as err:
                logger.error(
                    "Error syncing recent Garmin Connect health data for user",
                    exc_info=err,
                    extra=core_logger.context(user_id=user_id),
                )
        after_id = user_ids[-1]
