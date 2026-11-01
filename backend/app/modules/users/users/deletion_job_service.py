"""Queue account deletions so they never run on an API thread.

The request revokes the user's sessions and deactivates the account, so nobody can act as the user
while the data is erased, then answers 202. On the durable profile (``JOBS_ENABLED``) it stages a
``users.deletion_requested`` event and a worker runs it, surviving a restart. Otherwise the same body
runs on a small in-process pool that is not the request threadpool. Either way the state in the shared
state store is what an administrator polls, and its claim stops a user being queued twice.

The job erases the activities a batch per transaction, so no transaction holds the whole account, then
the profile photo, then deletes the user row, which removes everything else through the database
cascade. Every step can be repeated, so a job a worker died in is simply run again, and every step
that can fail runs while the row still marks the deletion, so the stalled-deletion sweep finds it.
"""

from datetime import timedelta

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import core.logger as core_logger
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.sign_up_tokens.integration_service as sign_up_tokens_integration
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.deletion_state_store as users_deletion_state_store
import modules.users.users.event_publishers as users_event_publishers
import modules.users.users.events as users_events
import modules.users.users.photo_service as users_photo_service
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

logger = core_logger.get_logger(__name__)

_Status = users_constants.DeletionStatus
_Kind = users_constants.DeletionKind


class _DeletionCancelledError(Exception):
    """An administrator reactivated the account, so the deletion queued for it must not go on."""


# Deletions are long and rare, so they get a pool of their own rather than the subscriber pool, where
# they would hold the threads that deliver notifications and thumbnails.
_deletion_pool = core_local_pool.BoundedPool(
    "user-deletion",
    workers=users_constants.DELETION_POOL_WORKERS,
    max_pending=users_constants.DELETION_POOL_MAX_PENDING,
)


def shutdown_deletion_pool(*, wait: bool = False) -> None:
    """Stop accepting deletions and release the pool thread.

    Args:
        wait: Whether to wait for a deletion still running.
    """
    _deletion_pool.shutdown(wait=wait)


def request_deletion(
    user_id: int,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    db: Session,
    *,
    if_match: str,
) -> users_schema.UserDeletionStatus:
    """Queue the erasure of a user's account and data.

    Signs the user out everywhere and deactivates the account before answering, so a deletion that
    is still running cannot be used. This is a unit of work: it commits.

    Args:
        user_id: The user to delete.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The deletion's initial status.

    Raises:
        NotFoundError: If the user does not exist.
        PreconditionFailedError: If the user changed since the client read it.
        ConflictError: If the user is the only administrator, or a deletion is already pending.
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    users_service.require_deletable_user(user_id, db, if_match=if_match)
    if not core_config.settings.JOBS_ENABLED:
        _deletion_pool.require_capacity()
    if not states.begin(user_id, _Kind.ACCOUNT):
        logger.debug(
            "Refused a second account deletion while one is pending", extra=core_logger.context(user_id=user_id)
        )
        raise core_exceptions.ConflictError("An account deletion is already in progress")

    try:
        account_security_integration.delete_all_user_sessions(user_id, db)
        sign_up_tokens_integration.revoke_pending_tokens(user_id, db)
        users_crud.stage_deletion_request(user_id, db)
        _dispatch(user_id, states, storage, db, source=users_constants.DELETION_SOURCE_API)
    except BaseException:
        # The deletion never started, so nothing else would finish its claim.
        states.set_status(user_id, _Kind.ACCOUNT, _Status.FAILED)
        raise

    logger.info("Account deletion queued", extra=core_logger.context(user_id=user_id))
    return users_schema.UserDeletionStatus(status=_Status.QUEUED)


def request_deletion_by_administrator(
    user_id: int,
    actor_id: int,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    db: Session,
    *,
    if_match: str,
) -> users_schema.UserDeletionStatus:
    """Queue the erasure of another user's account on an administrator's request.

    Args:
        user_id: The user to delete.
        actor_id: ID of the administrator making the request.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The deletion's initial status.

    Raises:
        PermissionDeniedError: If the administrator targets their own account, which needs step-up.
        NotFoundError: If the user does not exist.
        PreconditionFailedError: If the user changed since the client read it.
        ConflictError: If the user is the only administrator, or a deletion is already pending.
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    users_service.require_other_user(user_id, actor_id, "delete your account")
    with core_etag.refuse_stale_write(
        db, "user", lambda: users_crud.get_user_by_id(user_id, db) is not None, "User not found"
    ):
        return request_deletion(user_id, states, storage, db, if_match=if_match)


def _dispatch(
    user_id: int,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    db: Session,
    *,
    source: str,
) -> None:
    """Commit what the caller staged and hand the erasure to a worker, or to the in-process pool.

    Args:
        user_id: The user to delete.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        db: Database session holding the caller's staged writes.
        source: Who asked for the deletion, as recorded on the event.

    Raises:
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    if core_config.settings.JOBS_ENABLED:
        users_event_publishers.publish_deletion_requested(user_id, db, commit=db.commit, source=source)
        logger.debug("Account deletion queued for a worker", extra=core_logger.context(user_id=user_id, source=source))
        return
    db.commit()
    _deletion_pool.submit(run_deletion, users_events.DeletionRequestedPayload(user_id=user_id), states, storage)
    logger.debug(
        "Account deletion queued on the in-process pool", extra=core_logger.context(user_id=user_id, source=source)
    )


def get_deletion_status(
    user_id: int, states: users_deletion_state_store.UserDeletionStateStore
) -> users_schema.UserDeletionStatus:
    """Report where a user's account deletion is.

    Args:
        user_id: The user being deleted.
        states: Shared store of the deletion's state.

    Returns:
        The deletion's status.

    Raises:
        NotFoundError: When no deletion is recorded or it has expired.
    """
    state = states.get(user_id, _Kind.ACCOUNT)
    if state is None:
        raise core_exceptions.NotFoundError("No account deletion recorded")
    return users_schema.UserDeletionStatus(status=state.status)


def run_deletion(
    payload: users_events.DeletionRequestedPayload,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    *,
    will_retry: bool = False,
) -> None:
    """Erase one account and record the outcome. Blocking; call it from a worker, never a request.

    A deletion that raised and will be retried by a durable worker stays ``QUEUED`` with its claim held:
    releasing the claim would let a second deletion start beside the retry. One nothing will retry,
    because there is no worker or this was the last attempt, is ``FAILED`` and its claim is released;
    the account stays deactivated and an administrator deletes it again.

    Args:
        payload: Whose account to erase.
        states: Shared store of the deletion's state.
        storage: The platform storage provider.
        will_retry: Whether a durable worker runs this again if it raises.

    Raises:
        Exception: Whatever the deletion raised, when ``will_retry``, so the worker runs it again.
    """
    user_id = payload.user_id
    state = states.get(user_id, _Kind.ACCOUNT)
    if state is None or state.status not in (_Status.QUEUED, _Status.RUNNING):
        logger.debug("Skipped an account deletion that is not pending", extra=core_logger.context(user_id=user_id))
        return

    states.set_status(user_id, _Kind.ACCOUNT, _Status.RUNNING)
    try:
        activities = _erase_activities(user_id)
        _erase_photo(user_id, storage)
        _delete_user_row(user_id)
    except _DeletionCancelledError:
        states.discard(user_id, _Kind.ACCOUNT)
        logger.info("Account deletion cancelled by a reactivation", extra=core_logger.context(user_id=user_id))
        return
    except Exception as err:
        if will_retry:
            logger.warning(
                "Account deletion failed; it will be retried", exc_info=err, extra=core_logger.context(user_id=user_id)
            )
            states.set_status(user_id, _Kind.ACCOUNT, _Status.QUEUED)
            raise
        logger.error("Account deletion failed", exc_info=err, extra=core_logger.context(user_id=user_id))
        states.set_status(user_id, _Kind.ACCOUNT, _Status.FAILED)
        return

    users_contributor_registry.erasers().delete_staged_files(user_id, storage)
    states.set_status(user_id, _Kind.ACCOUNT, _Status.COMPLETED)
    logger.info("User deleted", extra=core_logger.context(user_id=user_id, activities=activities))


def _erase_activities(user_id: int) -> int:
    """Delete a user's activities one batch per transaction.

    Args:
        user_id: The user whose activities to delete.

    Returns:
        How many activities were deleted.

    Raises:
        _DeletionCancelledError: When the account was reactivated before a batch.
    """
    delete_batch = users_contributor_registry.erasers().delete_activities
    total = 0
    while True:
        with core_database.SessionLocal() as db:
            _require_not_cancelled(user_id, db)
            deleted = delete_batch(user_id, users_constants.DELETION_BATCH_SIZE, db)
            db.commit()
        if not deleted:
            return total
        total += deleted
        logger.debug(
            "Erased a batch of a user's activities",
            extra=core_logger.context(user_id=user_id, batch=deleted, total=total),
        )


def _require_not_cancelled(user_id: int, db: Session) -> None:
    """Stop the deletion when the account was reactivated; the row stays locked for the caller's transaction.

    Args:
        user_id: The user being deleted.
        db: Database session.

    Raises:
        _DeletionCancelledError: When the account is no longer queued for deletion.
    """
    if users_crud.is_deletion_cancelled(user_id, db):
        raise _DeletionCancelledError


def _erase_photo(user_id: int, storage: platform_providers.StorageProvider) -> None:
    """Clear the user's photo reference, then delete every photo blob under their prefix.

    The reference goes first, so a reactivation that stops the deletion afterwards leaves no row naming
    a blob that is gone. A storage failure is raised, so the deletion is retried.

    Args:
        user_id: The user whose photo to erase.
        storage: The platform storage provider.

    Raises:
        _DeletionCancelledError: When the account was reactivated.
    """
    with core_database.SessionLocal() as db:
        _require_not_cancelled(user_id, db)
        if users_crud.get_user_by_id(user_id, db) is not None:
            users_crud.replace_photo_key(user_id, None, db)
            db.commit()
    users_photo_service.delete_photo_files(user_id, storage)
    logger.debug("Erased the user's photo", extra=core_logger.context(user_id=user_id))


def _delete_user_row(user_id: int) -> None:
    """Delete the user row, which removes everything else that references it through the database cascade.

    A row that is already gone means an earlier attempt committed it, so there is nothing to do.

    Args:
        user_id: The user to delete.

    Raises:
        _DeletionCancelledError: When the account was reactivated.
    """
    with core_database.SessionLocal() as db:
        _require_not_cancelled(user_id, db)
        if users_crud.get_user_by_id(user_id, db) is None:
            logger.debug("The user row was already deleted", extra=core_logger.context(user_id=user_id))
            return
        users_crud.delete_user(user_id, db)
        db.commit()
    logger.debug("Deleted the user row", extra=core_logger.context(user_id=user_id))


def close_dead_lettered_deletion(
    payload: users_events.DeletionRequestedPayload, states: users_deletion_state_store.UserDeletionStateStore
) -> None:
    """Close a deletion the runner gave up on, so an administrator can queue it again.

    Runs however the last attempt ended, including a lease that expired or a worker that died, where
    :func:`run_deletion` never got to record it. A deletion that already finished, or whose state has
    expired, is left as it is.

    Args:
        payload: Whose account was to be erased.
        states: Shared store of the deletion's state.
    """
    if states.close_pending(payload.user_id, _Kind.ACCOUNT):
        logger.error("An account deletion was dead-lettered", extra=core_logger.context(user_id=payload.user_id))


def requeue_stalled_deletions(
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    clock: platform_providers.ClockProvider,
) -> int:
    """Queue again the deletions that never finished, up to ``DELETION_SWEEP_MAX_ATTEMPTS`` times each.

    The net for a deletion a worker dead-lettered, or whose in-process worker was lost with a restart:
    both leave the account deactivated and marked, with no job left to erase it. The claim keeps the
    sweep from queueing a deletion a live job still holds. An account the sweep has queued the maximum
    number of times is left for an administrator, who deletes it again.

    Args:
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        clock: The platform clock.

    Returns:
        How many deletions were queued again.
    """
    cutoff = clock.now() - timedelta(seconds=users_constants.DELETION_STALL_AFTER_SECONDS)
    queued = 0
    after_id = 0
    while True:
        with core_database.SessionLocal() as db:
            user_ids = users_crud.list_stalled_deletion_ids(
                cutoff,
                users_constants.DELETION_SWEEP_MAX_ATTEMPTS,
                after_id,
                users_constants.DELETION_SWEEP_BATCH_SIZE,
                db,
            )
        if not user_ids:
            break
        after_id = user_ids[-1]
        for user_id in user_ids:
            try:
                queued += _requeue(user_id, states, storage)
            except core_local_pool.PoolFullError:
                logger.warning("The deletion pool is full; the sweep stops until its next pass")
                return queued
    if queued:
        logger.info("Queued stalled account deletions again", extra=core_logger.context(count=queued))
    else:
        logger.debug("No stalled account deletions")
    return queued


def _requeue(
    user_id: int,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
) -> int:
    """Queue one stalled deletion again unless a job still holds it.

    A failure to queue it is logged and left for the next pass, so one account cannot stop the rest.

    Args:
        user_id: The user to delete.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.

    Returns:
        1 when the deletion was queued again, otherwise 0.

    Raises:
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    if not core_config.settings.JOBS_ENABLED:
        # Before the claim and the attempt are spent on a deletion nothing can run.
        _deletion_pool.require_capacity()
    if not states.begin(user_id, _Kind.ACCOUNT):
        logger.debug("A stalled deletion is still held by a job", extra=core_logger.context(user_id=user_id))
        return 0
    try:
        with core_database.SessionLocal() as db:
            attempts = users_crud.record_deletion_attempt(user_id, db)
            if attempts is None:
                # Gone, or an administrator reactivated the account: nothing is left to queue.
                states.set_status(user_id, _Kind.ACCOUNT, _Status.COMPLETED)
                return 0
            if attempts == users_constants.DELETION_SWEEP_MAX_ATTEMPTS:
                logger.error(
                    "Account deletion is on its last automatic attempt; an administrator must delete it again if "
                    "this fails",
                    extra=core_logger.context(user_id=user_id, attempts=attempts),
                )
            _dispatch(user_id, states, storage, db, source=users_constants.DELETION_SOURCE_SWEEP)
    except core_local_pool.PoolFullError:
        states.set_status(user_id, _Kind.ACCOUNT, _Status.FAILED)
        raise
    except Exception as err:
        states.set_status(user_id, _Kind.ACCOUNT, _Status.FAILED)
        logger.error(
            "Could not queue a stalled account deletion again", exc_info=err, extra=core_logger.context(user_id=user_id)
        )
        return 0
    logger.info("Queued a stalled account deletion again", extra=core_logger.context(user_id=user_id))
    return 1
