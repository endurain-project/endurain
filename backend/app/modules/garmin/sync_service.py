"""Queue Garmin Connect activity, gear and health syncs so they never run on an API thread.

On the durable profile (``JOBS_ENABLED``) the request stages a ``garmin.sync_requested`` event
and a worker runs it, surviving a restart. Otherwise the same body runs on a small in-process
pool that is not the request threadpool. Either way a gear or health sync is recorded in the
shared sync state, which the client polls and which stops a user queueing the same sync twice.
"""

from datetime import UTC, date, datetime, timedelta

import garminconnect
import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import core.logger as core_logger
import core.sync_runner as core_sync_runner
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.garmin.constants as garmin_constants
import modules.garmin.event_publishers as garmin_event_publishers
import modules.garmin.events as garmin_events
import modules.garmin.gear_service as garmin_gear_service
import modules.garmin.health_service as garmin_health_service
import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.schema as garmin_schema
import modules.garmin.service as garmin_service
import modules.garmin.sync_state_store as garmin_sync_state_store
import modules.users.users.integration_service as users_integration
import modules.websocket.constants as websocket_constants
import modules.websocket.integration_service as websocket_integration

logger = core_logger.get_logger(__name__)

_sync_pool = core_sync_runner.sync_pool("garmin-sync")

_USERS_PAGE_SIZE = 100


def shutdown_sync_pool(*, wait: bool = False) -> None:
    """Stop accepting syncs and release the pool threads.

    Args:
        wait: Whether to wait for syncs still running.
    """
    _sync_pool.shutdown(wait=wait)


def run_sync(
    payload: garmin_events.SyncRequestedPayload,
    states: garmin_sync_state_store.GarminSyncStateStore,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
    *,
    will_retry: bool = False,
) -> None:
    """Run one queued sync and record its outcome. Blocking; call it from a worker, never a request.

    A sync that could not run because the account is not linked, Garmin Connect rejected its
    token or Garmin Connect is rate limiting the account is recorded as failed and not raised: a
    retry would meet the same answer.

    A sync that raised and will be retried by a durable worker stays ``QUEUED`` with its claim held:
    releasing the claim would let a second sync start beside the retry. A sync nothing will retry,
    because there is no worker or this was the last attempt, is ``FAILED`` and its claim is released.

    Args:
        payload: What to sync.
        states: Shared store of the sync's state.
        rate_limits: The shared Garmin Connect rate-limit state.
        will_retry: Whether a durable worker runs this again if it raises.

    Raises:
        Exception: Whatever the sync raised, after recording its state, so a durable worker retries it.
    """

    def work() -> bool:
        """Run the gear or health sync the payload asks for.

        Returns:
            Whether the sync did anything.
        """
        if payload.kind == garmin_constants.SyncKind.GEAR:
            return garmin_gear_service.get_user_gear(payload.user_id, rate_limits)
        if payload.start_date is not None and payload.end_date is not None:
            return garmin_health_service.sync_health_for_dates(
                payload.start_date, payload.end_date, payload.user_id, rate_limits
            )
        return False

    def record_refusal(err: Exception) -> None:
        """Record a Garmin Connect rate limit for every process.

        Args:
            err: The error that made Garmin Connect or the rate-limit state refuse the sync.
        """
        if isinstance(err, garminconnect.GarminConnectTooManyRequestsError):
            # Recorded for every process, so the next sync waits out the cooldown instead of meeting the limit again.
            garmin_service.rate_limit_error(err, payload.user_id, rate_limits)

    synced = core_sync_runner.run_recorded(
        states,
        payload.user_id,
        payload.kind,
        work,
        will_retry=will_retry,
        refusals=(garminconnect.GarminConnectTooManyRequestsError, core_exceptions.TooManyRequestsError),
        on_refused=record_refusal,
    )
    if synced:
        # Best effort: the synced rows are already committed, so a lost hint only delays the refresh.
        websocket_integration.push_to_user(
            payload.user_id,
            {
                "message": websocket_constants.GEARS_CHANGED_MESSAGE
                if payload.kind == garmin_constants.SyncKind.GEAR
                else websocket_constants.HEALTH_CHANGED_MESSAGE
            },
        )


def close_dead_lettered_sync(
    payload: garmin_events.SyncRequestedPayload, states: garmin_sync_state_store.GarminSyncStateStore
) -> None:
    """Close a sync the runner gave up on, so the user can queue another.

    Runs however the last attempt ended, including a lease that expired or a worker that died, where
    :func:`run_sync` never got to record it. A sync that already finished, or whose state has expired,
    is left as it is, and so is a newer sync that took its claim.

    Args:
        payload: What was to be synced.
        states: Shared store of the sync's state.
    """
    core_sync_runner.close_dead_lettered(states, payload.user_id, payload.kind, "Garmin Connect")


def _queue(
    user_id: int,
    kind: garmin_constants.SyncKind,
    start_date: date | None,
    end_date: date | None,
    states: garmin_sync_state_store.GarminSyncStateStore,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
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
        rate_limits: The shared Garmin Connect rate-limit state, for the in-process pool.
        db: Database session.
        source: Who asked for the sync, as recorded on the event.
        wait_seconds: How long to wait for a pool slot when the pool is full.

    Returns:
        The sync's initial status.

    Raises:
        ConflictError: When a sync of this kind is already pending for the user.
        PoolFullError: When the in-process pool is still full after the wait.
    """
    core_sync_runner.queue_sync(
        states,
        user_id,
        kind,
        "Garmin Connect",
        durable=core_config.settings.JOBS_ENABLED,
        publish=lambda: garmin_event_publishers.publish_sync_requested(
            user_id, kind, start_date, end_date, db, commit=db.commit, source=source
        ),
        submit=lambda: _sync_pool.submit(
            run_sync,
            garmin_events.SyncRequestedPayload(user_id=user_id, kind=kind, start_date=start_date, end_date=end_date),
            states,
            rate_limits,
            wait_seconds=wait_seconds,
        ),
    )
    logger.info(
        "Garmin Connect sync queued",
        extra=core_logger.context(user_id=user_id, kind=kind, durable=core_config.settings.JOBS_ENABLED),
    )
    return garmin_schema.GarminSyncStatus(kind=kind, status=garmin_constants.SyncStatus.QUEUED)


def request_gear_sync(
    user_id: int,
    states: garmin_sync_state_store.GarminSyncStateStore,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
    db: Session,
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect gear.

    Args:
        user_id: The user to sync.
        states: Shared store of the sync's state.
        rate_limits: The shared Garmin Connect rate-limit state.
        db: Database session.

    Returns:
        The sync's initial status.
    """
    return _queue(user_id, garmin_constants.SyncKind.GEAR, None, None, states, rate_limits, db)


def request_health_sync(
    user_id: int,
    start_date: date,
    end_date: date,
    states: garmin_sync_state_store.GarminSyncStateStore,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
    db: Session,
) -> garmin_schema.GarminSyncStatus:
    """Queue a sync of the user's Garmin Connect health data for a range of days.

    Args:
        user_id: The user to sync.
        start_date: First day of the range.
        end_date: Last day of the range.
        states: Shared store of the sync's state.
        rate_limits: The shared Garmin Connect rate-limit state.
        db: Database session.

    Returns:
        The sync's initial status.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date``, ``end_date`` is in the future or the
            range is longer than ``MAX_HEALTH_RANGE_DAYS``.
    """
    core_sync_runner.validate_range(
        start_date,
        end_date,
        garmin_constants.MAX_HEALTH_RANGE_DAYS,
        users_integration.local_today(user_id, db),
    )
    return _queue(user_id, garmin_constants.SyncKind.HEALTH, start_date, end_date, states, rate_limits, db)


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
    state = core_sync_runner.read_state(states, user_id, kind, "Garmin Connect")
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
    capped, so a first sync that reaches back years is made in several requests.

    Args:
        user_id: The user to sync.
        start_date: First day of the range.
        end_date: Last day of the range.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The queued job's handle.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date``, ``end_date`` is in the future or the
            range is longer than ``MAX_ACTIVITIES_RANGE_DAYS``.
    """
    core_sync_runner.validate_range(
        start_date,
        end_date,
        core_sync_runner.MAX_ACTIVITIES_RANGE_DAYS,
        users_integration.local_today(user_id, db),
    )

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


def _sync_recent_health_for_user(
    user_id: int,
    states: garmin_sync_state_store.GarminSyncStateStore,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
) -> None:
    """Queue one user's recent health data for a worker, or for the in-process pool without durable jobs.

    The window is yesterday and today in the user's own timezone, as Garmin Connect dates its
    records by the user's day. A user whose health sync is still pending is skipped: the window
    overlaps the next run, so nothing is lost.

    Args:
        user_id: The user to sync.
        states: Shared store of the sync's state.
        rate_limits: The shared Garmin Connect rate-limit state.

    Raises:
        PoolFullError: When the in-process pool stayed full for the whole wait.
    """
    with core_database.SessionLocal() as db:
        end_date = users_integration.local_today(user_id, db)
        # Return the connection to the pool now: queueing may wait minutes for a pool slot.
        db.close()
        try:
            _queue(
                user_id,
                garmin_constants.SyncKind.HEALTH,
                end_date - timedelta(days=1),
                end_date,
                states,
                rate_limits,
                db,
                source=garmin_constants.SYNC_SOURCE_SCHEDULER,
                wait_seconds=garmin_constants.SCHEDULED_SLOT_WAIT_SECONDS,
            )
        except core_exceptions.ConflictError:
            logger.debug("Garmin Connect health sync already pending", extra=core_logger.context(user_id=user_id))


def sync_recent_health(
    states: garmin_sync_state_store.GarminSyncStateStore,
    rate_limits: garmin_rate_limit_store.GarminRateLimitStore,
) -> None:
    """Sync the last day of Garmin Connect health stats for every linked user.

    Each user's sync is queued, for a worker with durable jobs or for the in-process pool without
    them, so users are isolated and never run on this thread. Linked users are read a page at a
    time in short sessions, and one user failing does not stop the rest. Without durable jobs a
    full pool is waited on; if it stays full the pass stops, and the next run starts over.

    Args:
        states: Shared store of the syncs' state.
        rate_limits: The shared Garmin Connect rate-limit state.
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
                _sync_recent_health_for_user(user_id, states, rate_limits)
            except core_local_pool.PoolFullError:
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
