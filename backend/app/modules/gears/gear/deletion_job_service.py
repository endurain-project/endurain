"""Queue a gear deletion so it never runs on an API thread.

Deleting a gear unassigns it from every activity that carries it, which for a bike can be thousands of rows and as
many ``activity.updated`` events, so the request answers 202 and the work runs elsewhere. On the durable profile
(``JOBS_ENABLED``) it stages a ``gears.deletion_requested`` event and a worker runs it, surviving a restart.
Otherwise the same body runs on a small in-process pool that is not the request threadpool. Either way the state in
the shared state store is what the client polls, and its claim stops the same gear being queued twice.

The request checks that the gear is the user's and that ``If-Match`` names its current version before it queues
anything, so a stale write is refused up front. The job unassigns the gear from the activities a batch per
transaction, each batch staging its ``activity.updated`` events with it, then in one last transaction clears
whatever was assigned meanwhile, clears the default gear settings, records the components' deletion and deletes
the gear. A batch that finds nothing left changes nothing, and a gear that is already gone ends the job as
succeeded, so every step can be repeated and a job a worker died in is simply run again.
"""

import uuid

from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import core.local_pool as core_local_pool
import core.logger as core_logger
import modules.gears.contributor_registry as gears_contributor_registry
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.deletion_state_store as deletion_state_store
import modules.gears.gear.event_publishers as gears_event_publishers
import modules.gears.gear.events as gears_events
import modules.gears.gear.schema as gears_schema
import modules.gears.gear.service as gears_service

logger = core_logger.get_logger(__name__)

_Status = core_job_status.JobState

# Deletions are rare and can be long, so they get a pool of their own rather than the subscriber pool, where they
# would hold the threads that deliver notifications and thumbnails.
_pool = core_local_pool.BoundedPool(
    "gear-deletion",
    workers=gears_constants.DELETION_POOL_WORKERS,
    max_pending=gears_constants.DELETION_POOL_MAX_PENDING,
)


def shutdown_pool(*, wait: bool = False) -> None:
    """Stop accepting deletions and release the pool thread.

    Args:
        wait: Whether to wait for a deletion still running.
    """
    _pool.shutdown(wait=wait)


def request_gear_deletion(
    gear_id: uuid.UUID,
    user_id: uuid.UUID,
    states: deletion_state_store.GearDeletionStateStore,
    db: Session,
    *,
    if_match: str,
) -> gears_schema.GearDeletionStatus:
    """Queue the deletion of a user's gear after checking it is theirs and unchanged.

    Args:
        gear_id: Gear ID to delete.
        user_id: Owner user ID.
        states: Shared store of the deletion's state.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The deletion's initial status.

    Raises:
        NotFoundError: If the user has no such gear.
        PreconditionFailedError: If the gear changed since the client read it.
        JobAlreadyRunningError: When a deletion of the gear is already pending.
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    gear = gears_crud.get_gear_user_by_id(user_id, gear_id, db)
    if gear is None:
        raise core_exceptions.NotFoundError("Gear not found")
    core_etag.require_if_match(if_match, gear.version, "gear")

    durable = core_config.settings.JOBS_ENABLED
    if not durable:
        _pool.require_capacity()
    job = states.begin(gear_id, user_id, conflict="A deletion of this gear is already in progress")

    try:
        if durable:
            gears_event_publishers.publish_deletion_requested(gear_id, user_id, job.id, db, commit=db.commit)
        else:
            _pool.submit(
                run_gear_deletion,
                gears_events.DeletionRequestedPayload(user_id=user_id, gear_id=gear_id, job_id=job.id),
                states,
            )
    except BaseException:
        # The deletion never started, so nothing else would finish its claim.
        states.set_status(gear_id, job.id, _Status.FAILED)
        raise

    logger.info("Gear deletion queued", extra=core_logger.context(user_id=user_id, gear_id=gear_id, durable=durable))
    return gears_schema.GearDeletionStatus.model_validate({**job.envelope(), "status": _Status.QUEUED})


def run_gear_deletion(
    payload: gears_events.DeletionRequestedPayload,
    states: deletion_state_store.GearDeletionStateStore,
    *,
    will_retry: bool = False,
) -> None:
    """Delete a gear and record the outcome. Blocking; call it from a worker.

    A deletion that raised and will be retried by a durable worker stays ``QUEUED`` with its claim held:
    releasing the claim would let a second deletion start beside the retry. One nothing will retry, because
    there is no worker or this was the last attempt, is ``FAILED`` and its claim is released.

    Args:
        payload: The gear to delete and its owner.
        states: Shared store of the deletion's state.
        will_retry: Whether a durable worker runs this again if it raises.

    Raises:
        Exception: Whatever the deletion raised, when ``will_retry``, so the worker runs it again.
    """
    gear_id, job_id = payload.gear_id, payload.job_id
    state = states.get(gear_id, job_id=job_id)
    if state is None or state.status not in (_Status.QUEUED, _Status.RUNNING):
        logger.debug("Skipped a gear deletion that is not pending", extra=core_logger.context(gear_id=gear_id))
        return

    states.set_status(gear_id, job_id, _Status.RUNNING)
    try:
        unassigned, deleted = _apply(payload.user_id, gear_id)
    except Exception as err:
        if will_retry:
            logger.warning(
                "Gear deletion failed; it will be retried",
                exc_info=err,
                extra=core_logger.context(user_id=payload.user_id, gear_id=gear_id),
            )
            states.set_status(gear_id, job_id, _Status.QUEUED)
            raise
        logger.error(
            "Gear deletion failed",
            exc_info=err,
            extra=core_logger.context(user_id=payload.user_id, gear_id=gear_id),
        )
        states.set_status(gear_id, job_id, _Status.FAILED)
        return

    states.set_status(gear_id, job_id, _Status.SUCCEEDED)
    logger.info(
        "Gear deletion finished",
        extra=core_logger.context(user_id=payload.user_id, gear_id=gear_id, unassigned=unassigned, deleted=deleted),
    )


def _apply(user_id: uuid.UUID, gear_id: uuid.UUID) -> tuple[int, bool]:
    """Unassign a gear from the activities a batch per transaction, then delete it.

    Args:
        user_id: The gear's owner.
        gear_id: The gear to delete.

    Returns:
        How many activities the gear was unassigned from, and whether this call deleted the gear, which is
        false when it was already gone.
    """
    unassigned = _unassign_in_batches(user_id, gear_id)
    with core_database.SessionLocal() as db:
        try:
            # The version was checked when the deletion was accepted; the gear may have been edited since.
            gears_service.delete_gear(gear_id, user_id, db, if_match=core_etag.WILDCARD)
        except core_exceptions.NotFoundError:
            logger.debug("Skipped deleting a gear that is already gone", extra=core_logger.context(gear_id=gear_id))
            return unassigned, False
    return unassigned, True


def _unassign_in_batches(user_id: uuid.UUID, gear_id: uuid.UUID) -> int:
    """Unassign a gear from the activities that carry it, a batch per transaction.

    Args:
        user_id: The gear's owner.
        gear_id: The gear being deleted.

    Returns:
        How many activities were unassigned.
    """
    clear = gears_contributor_registry.readers().clear_activities_gear
    total = 0
    while True:
        with core_database.SessionLocal() as db:
            cleared = clear(gear_id, user_id, gears_constants.DELETION_BATCH_SIZE, db)
            db.commit()
        total += cleared
        logger.debug(
            "Unassigned a gear from a batch of activities",
            extra=core_logger.context(gear_id=gear_id, batch=cleared, total=total),
        )
        if cleared < gears_constants.DELETION_BATCH_SIZE:
            return total


def close_dead_lettered_deletion(
    payload: gears_events.DeletionRequestedPayload, states: deletion_state_store.GearDeletionStateStore
) -> None:
    """Close a deletion the runner gave up on, so the user can queue it again.

    Runs however the last attempt ended, including a lease that expired or a worker that died, where
    :func:`run_gear_deletion` never got to record it. A deletion that already finished, or whose state has
    expired, is left as it is.

    Args:
        payload: The gear that was to be deleted.
        states: Shared store of the deletion's state.
    """
    if states.close_pending(payload.gear_id, payload.job_id):
        logger.error(
            "A gear deletion was dead-lettered",
            extra=core_logger.context(user_id=payload.user_id, gear_id=payload.gear_id),
        )
