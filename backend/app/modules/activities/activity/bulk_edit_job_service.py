"""Queue a bulk visibility edit so it never runs on an API thread.

Changing the visibility of every activity a user owns can touch tens of thousands of rows, so the request
answers 202 and the work runs elsewhere. On the durable profile (``JOBS_ENABLED``) it stages an
``activities.visibility_edit_requested`` event and a worker runs it, surviving a restart. Otherwise the same
body runs on a small in-process pool that is not the request threadpool. Either way the state in the shared
state store is what the client polls, and its claim stops the same edit being queued twice.

The job changes the activities a batch per transaction and publishes one ``activity.updated`` per changed
row with that batch, so no transaction holds a whole library. Only activities that do not have the
visibility yet are touched, so every step can be repeated and a job a worker died in is simply run again.
"""

from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import core.logger as core_logger
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.bulk_edit_state_store as bulk_edit_state_store
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.events as activity_events
import modules.activities.activity.schema as activity_schema

logger = core_logger.get_logger(__name__)

_Status = bulk_edit_constants.BulkEditStatus
_Kind = bulk_edit_constants.BulkEditKind.VISIBILITY

# Edits are long and rare, so they get a pool of their own rather than the subscriber pool, where they
# would hold the threads that deliver notifications and thumbnails.
_pool = core_local_pool.BoundedPool(
    "activity-bulk-edit",
    workers=bulk_edit_constants.BULK_EDIT_POOL_WORKERS,
    max_pending=bulk_edit_constants.BULK_EDIT_POOL_MAX_PENDING,
)


def shutdown_pool(*, wait: bool = False) -> None:
    """Stop accepting edits and release the pool thread.

    Args:
        wait: Whether to wait for an edit still running.
    """
    _pool.shutdown(wait=wait)


def request_visibility_edit(
    user_id: int,
    visibility: int,
    states: bulk_edit_state_store.ActivityBulkEditStateStore,
    db: Session,
) -> activity_schema.ActivitiesBulkEditStatus:
    """Queue the visibility change of all of a user's activities.

    Args:
        user_id: The user whose activities to edit.
        visibility: The visibility to apply: 0 public, 1 followers, 2 private.
        states: Shared store of the edit's state.
        db: Database session.

    Returns:
        The edit's initial status.

    Raises:
        ConflictError: When an edit is already pending for the user.
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    durable = core_config.settings.JOBS_ENABLED
    if not durable:
        _pool.require_capacity()
    if not states.begin(user_id, _Kind):
        logger.debug("Refused a second bulk edit while one is pending", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.ConflictError("A bulk edit is already in progress")

    try:
        if durable:
            activity_event_publishers.publish_visibility_edit_requested(user_id, visibility, db, commit=db.commit)
        else:
            _pool.submit(
                run_visibility_edit,
                activity_events.VisibilityEditRequestedPayload(user_id=user_id, visibility=visibility),
                states,
            )
    except BaseException:
        # The edit never started, so nothing else would finish its claim.
        states.set_status(user_id, _Kind, _Status.FAILED)
        raise

    logger.info(
        "Bulk visibility edit queued",
        extra=core_logger.context(user_id=user_id, visibility=visibility, durable=durable),
    )
    return activity_schema.ActivitiesBulkEditStatus(status=_Status.QUEUED)


def get_visibility_edit_status(
    user_id: int, states: bulk_edit_state_store.ActivityBulkEditStateStore
) -> activity_schema.ActivitiesBulkEditStatus:
    """Report where a user's bulk visibility edit is.

    Args:
        user_id: The user whose edit to report.
        states: Shared store of the edit's state.

    Returns:
        The edit's status.

    Raises:
        NotFoundError: When no edit is recorded or it has expired.
    """
    state = states.get(user_id, _Kind)
    if state is None:
        raise core_exceptions.NotFoundError("No bulk edit recorded")
    return activity_schema.ActivitiesBulkEditStatus(status=state.status)


def run_visibility_edit(
    payload: activity_events.VisibilityEditRequestedPayload,
    states: bulk_edit_state_store.ActivityBulkEditStateStore,
    *,
    will_retry: bool = False,
) -> None:
    """Apply a visibility to a user's activities and record the outcome. Blocking; call it from a worker.

    An edit that raised and will be retried by a durable worker stays ``QUEUED`` with its claim held:
    releasing the claim would let a second edit start beside the retry. One nothing will retry, because
    there is no worker or this was the last attempt, is ``FAILED`` and its claim is released.

    Args:
        payload: Whose activities to edit and the visibility to apply.
        states: Shared store of the edit's state.
        will_retry: Whether a durable worker runs this again if it raises.

    Raises:
        Exception: Whatever the edit raised, when ``will_retry``, so the worker runs it again.
    """
    user_id = payload.user_id
    state = states.get(user_id, _Kind)
    if state is None or state.status not in (_Status.QUEUED, _Status.RUNNING):
        logger.debug("Skipped a bulk edit that is not pending", extra=core_logger.context(user_id=user_id))
        return

    states.set_status(user_id, _Kind, _Status.RUNNING)
    try:
        updated = _apply(user_id, payload.visibility)
    except Exception as err:
        if will_retry:
            logger.warning(
                "Bulk visibility edit failed; it will be retried",
                exc_info=err,
                extra=core_logger.context(user_id=user_id),
            )
            states.set_status(user_id, _Kind, _Status.QUEUED)
            raise
        logger.error("Bulk visibility edit failed", exc_info=err, extra=core_logger.context(user_id=user_id))
        states.set_status(user_id, _Kind, _Status.FAILED)
        return

    states.set_status(user_id, _Kind, _Status.COMPLETED)
    logger.info(
        "Bulk visibility edit finished",
        extra=core_logger.context(user_id=user_id, visibility=payload.visibility, updated=updated),
    )


def _apply(user_id: int, visibility: int) -> int:
    """Change a user's activities one batch per transaction.

    Args:
        user_id: The user whose activities to edit.
        visibility: The visibility to apply.

    Returns:
        How many activities changed.
    """
    total = 0
    while True:
        with core_database.SessionLocal() as db:
            updated_ids = activity_crud.edit_user_activities_visibility_batch(
                user_id, visibility, bulk_edit_constants.BULK_EDIT_BATCH_SIZE, db
            )
            if updated_ids:
                activity_event_publishers.publish_activities_updated(
                    updated_ids,
                    user_id,
                    db,
                    changed_fields=["visibility"],
                    source=bulk_edit_constants.BULK_EDIT_SOURCE,
                )
            db.commit()
        if not updated_ids:
            return total
        total += len(updated_ids)
        logger.debug(
            "Changed a batch of a user's activities",
            extra=core_logger.context(user_id=user_id, batch=len(updated_ids), total=total),
        )


def close_dead_lettered_visibility_edit(
    payload: activity_events.VisibilityEditRequestedPayload,
    states: bulk_edit_state_store.ActivityBulkEditStateStore,
) -> None:
    """Close an edit the runner gave up on, so the user can queue it again.

    Runs however the last attempt ended, including a lease that expired or a worker that died, where
    :func:`run_visibility_edit` never got to record it. An edit that already finished, or whose state has
    expired, is left as it is.

    Args:
        payload: Whose activities were to be edited.
        states: Shared store of the edit's state.
    """
    if states.close_pending(payload.user_id, _Kind):
        logger.error("A bulk visibility edit was dead-lettered", extra=core_logger.context(user_id=payload.user_id))
