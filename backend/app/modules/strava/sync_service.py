"""Queue Strava gear syncs and unlinks so they never run on an API thread.

On the durable profile (``JOBS_ENABLED``) the request stages a ``strava.sync_requested`` event
and a worker runs it, surviving a restart. Otherwise the same body runs on a small in-process
pool that is not the request threadpool. Either way the sync is recorded in the shared sync
state, which the client polls and which stops a user queueing the same sync twice.
"""

from sqlalchemy.orm import Session

import core.config as core_config
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import core.logger as core_logger
import modules.strava.constants as strava_constants
import modules.strava.event_publishers as strava_event_publishers
import modules.strava.events as strava_events
import modules.strava.gear_service as strava_gear_service
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service
import modules.strava.sync_state_store as strava_sync_state_store
import modules.websocket.constants as websocket_constants
import modules.websocket.integration_service as websocket_integration

logger = core_logger.get_logger(__name__)

# Small on purpose: syncs are Strava round trips and compete with the request threads.
_sync_pool = core_local_pool.BoundedPool("strava-sync", workers=2, max_pending=strava_constants.MAX_PENDING_LOCAL_SYNCS)


def shutdown_sync_pool(*, wait: bool = False) -> None:
    """Stop accepting syncs and release the pool threads.

    Args:
        wait: Whether to wait for syncs still running.
    """
    _sync_pool.shutdown(wait=wait)


def run_sync(
    payload: strava_events.SyncRequestedPayload,
    states: strava_sync_state_store.StravaSyncStateStore,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
    *,
    will_retry: bool = False,
) -> None:
    """Run one queued sync and record its outcome. Blocking; call it from a worker, never a request.

    A sync that could not run because Strava is rate limiting the application is recorded as
    failed and not raised: a retry would meet the same answer.

    A sync that raised and will be retried by a durable worker stays ``QUEUED`` with its claim held:
    releasing the claim would let a second sync start beside the retry. A sync nothing will retry,
    because there is no worker or this was the last attempt, is ``FAILED`` and its claim is released.

    Args:
        payload: What to sync.
        states: Shared store of the sync's state.
        rate_limits: The shared Strava rate-limit state.
        will_retry: Whether a durable worker runs this again if it raises.

    Raises:
        ValueError: When ``payload`` is a link, which never runs as a sync job.
        Exception: Whatever the sync raised, after recording its state, so a durable worker retries it.
    """
    if payload.kind == strava_constants.SyncKind.LINK:
        raise ValueError("A Strava link runs on the link pool, not as a sync job")
    states.set_status(payload.user_id, payload.kind, strava_constants.SyncStatus.RUNNING)
    try:
        if payload.kind == strava_constants.SyncKind.GEAR:
            synced = strava_gear_service.get_user_gear(payload.user_id, rate_limits)
        else:
            strava_service.unlink_account(payload.user_id)
            synced = True
    except core_exceptions.TooManyRequestsError:
        logger.warning(
            "Strava refused the sync: rate limit",
            extra=core_logger.context(user_id=payload.user_id, kind=payload.kind),
        )
        states.set_status(payload.user_id, payload.kind, strava_constants.SyncStatus.FAILED)
        return
    except Exception:
        states.set_status(
            payload.user_id,
            payload.kind,
            strava_constants.SyncStatus.QUEUED if will_retry else strava_constants.SyncStatus.FAILED,
        )
        raise
    outcome = strava_constants.SyncStatus.COMPLETED if synced else strava_constants.SyncStatus.FAILED
    states.set_status(payload.user_id, payload.kind, outcome)
    if payload.kind == strava_constants.SyncKind.UNLINK:
        websocket_integration.push_job_changed(payload.user_id, strava_constants.UNLINK_JOB)
    if synced and payload.kind == strava_constants.SyncKind.GEAR:
        # Best effort: the synced rows are already committed, so a lost hint only delays the refresh.
        websocket_integration.push_to_user(payload.user_id, {"message": websocket_constants.GEARS_CHANGED_MESSAGE})


def close_dead_lettered_sync(
    payload: strava_events.SyncRequestedPayload, states: strava_sync_state_store.StravaSyncStateStore
) -> None:
    """Close a sync the runner gave up on, so the user can queue another.

    Runs however the last attempt ended, including a lease that expired or a worker that died, where
    :func:`run_sync` never got to record it. A sync that already finished, or whose state has expired,
    is left as it is, and so is a newer sync that took its claim.

    Args:
        payload: What was to be synced.
        states: Shared store of the sync's state.
    """
    if states.close_pending(payload.user_id, payload.kind):
        logger.error(
            "A Strava sync was dead-lettered", extra=core_logger.context(user_id=payload.user_id, kind=payload.kind)
        )


def _queue(
    user_id: int,
    kind: strava_constants.SyncKind,
    states: strava_sync_state_store.StravaSyncStateStore,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
    db: Session,
) -> strava_schema.StravaSyncStatus:
    """Hand a sync to a worker, or to the in-process pool without durable jobs.

    Args:
        user_id: The user to sync.
        kind: What to do.
        states: Shared store of the sync's state.
        rate_limits: The shared Strava rate-limit state, for the in-process pool.
        db: Database session.

    Returns:
        The sync's initial status.

    Raises:
        ConflictError: When a sync of this kind is already pending for the user.
        PoolFullError: When the in-process pool is full.
    """
    if not states.begin(user_id, kind):
        raise core_exceptions.ConflictError(f"A Strava {kind.value} sync is already in progress")
    try:
        if core_config.settings.JOBS_ENABLED:
            strava_event_publishers.publish_sync_requested(
                user_id, kind, db, commit=db.commit, source=strava_constants.SYNC_SOURCE_API
            )
            logger.info("Strava sync queued for a worker", extra=core_logger.context(user_id=user_id, kind=kind))
        else:
            payload = strava_events.SyncRequestedPayload(user_id=user_id, kind=kind)
            _sync_pool.submit(run_sync, payload, states, rate_limits)
            logger.info(
                "Strava sync queued on the in-process pool", extra=core_logger.context(user_id=user_id, kind=kind)
            )
    except BaseException:
        # The sync never started, so nothing else would finish its claim.
        states.set_status(user_id, kind, strava_constants.SyncStatus.FAILED)
        raise
    return strava_schema.StravaSyncStatus(kind=kind, status=strava_constants.SyncStatus.QUEUED)


def request_gear_sync(
    user_id: int,
    states: strava_sync_state_store.StravaSyncStateStore,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
    db: Session,
) -> strava_schema.StravaSyncStatus:
    """Queue a sync of the user's Strava gear.

    Args:
        user_id: The user to sync.
        states: Shared store of the sync's state.
        rate_limits: The shared Strava rate-limit state.
        db: Database session.

    Returns:
        The sync's initial status.
    """
    return _queue(user_id, strava_constants.SyncKind.GEAR, states, rate_limits, db)


def request_unlink(
    user_id: int,
    states: strava_sync_state_store.StravaSyncStateStore,
    rate_limits: strava_rate_limit_store.StravaRateLimitStore,
    db: Session,
) -> strava_schema.StravaSyncStatus:
    """Queue the unlinking of the user's Strava account and the deletion of what was imported from it.

    Args:
        user_id: The user to unlink.
        states: Shared store of the sync's state.
        rate_limits: The shared Strava rate-limit state.
        db: Database session.

    Returns:
        The unlink's initial status.
    """
    return _queue(user_id, strava_constants.SyncKind.UNLINK, states, rate_limits, db)


def get_sync_status(
    user_id: int, kind: strava_constants.SyncKind, states: strava_sync_state_store.StravaSyncStateStore
) -> strava_schema.StravaSyncStatus:
    """Report where a user's gear sync or unlink is.

    Args:
        user_id: The user being synced.
        kind: What the sync does.
        states: Shared store of the sync's state.

    Returns:
        The sync's status.

    Raises:
        NotFoundError: When no sync is recorded or it has expired.
    """
    state = states.get(user_id, kind)
    if state is None:
        raise core_exceptions.NotFoundError(f"No Strava {kind.value} sync recorded")
    return strava_schema.StravaSyncStatus(kind=kind, status=state.status)
