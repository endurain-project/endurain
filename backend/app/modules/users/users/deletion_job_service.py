"""Queue account deletions so they never run on an API thread.

The request revokes the user's sessions and deactivates the account, so nobody can act as the user
while the data is erased, then answers 202. On the durable profile (``JOBS_ENABLED``) it stages a
``users.deletion_requested`` event and a worker runs it, surviving a restart. Otherwise the same body
runs on a small in-process pool that is not the request threadpool. Either way the state in the shared
state store is what an administrator polls, and its claim stops a user being queued twice.

The job erases the activities a batch per transaction, so no transaction holds the whole account. On the
durable profile a pass stops at a time budget with activities left and the worker continues the same job
(see :func:`durable_pass_seconds`). Once no activities are left it erases the profile photo, then deletes
the user row, which removes everything else through the database cascade. Every step can be repeated, so a job a worker died in is simply run again, and every step
that can fail runs while the row still marks the deletion, so the stalled-deletion sweep finds it.
"""

import time
import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

import jasil.audit as jasil_audit
import jasil.providers as platform_providers
from sqlalchemy import Select
from sqlalchemy.orm import Session

import core.config as core_config
import core.database as core_database
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.job_status as core_job_status
import core.local_pool as core_local_pool
import core.logger as core_logger
import core.mail as core_mail
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.schema as auth_schema
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sign_up_tokens.integration_service as sign_up_tokens_integration
import modules.server_settings.integration_service as server_settings_integration
import modules.users.contributor_registry as users_contributor_registry
import modules.users.users.audit_actions as users_audit_actions
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


_CONFLICT = "An account deletion is already in progress"


def _status(job: core_job_status.JobRef, status: _Status) -> users_schema.UserDeletionStatus:
    """Build the status of a deletion job.

    Args:
        job: The deletion job's reference.
        status: Where the deletion is.

    Returns:
        The deletion's status.
    """
    return users_schema.UserDeletionStatus.model_validate({**job.envelope(), "status": status})


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
    user_id: uuid.UUID,
    owner_id: uuid.UUID,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    mail: platform_providers.MailProvider,
    db: Session,
    *,
    if_match: str,
) -> users_schema.UserDeletionStatus:
    """Queue the erasure of a user's account and data.

    Signs the user out everywhere and deactivates the account before answering, so a deletion that
    is still running cannot be used. This is a unit of work: it commits.

    Args:
        user_id: The user to delete.
        owner_id: The user who asked for the deletion and may read the job: an administrator, or the user.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        mail: The platform mail provider, for the in-process pool.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The deletion's initial status, with the id of the job that reads it.

    Raises:
        NotFoundError: If the user does not exist.
        PreconditionFailedError: If the user changed since the client read it.
        LastAdministratorError: If the user is the only administrator.
        JobAlreadyRunningError: If a deletion is already pending.
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    users_service.require_user(user_id, db)
    # The generation row is locked before the administrator rows that the deletable check locks.
    security_generation_integration.stage_bump(user_id, db)
    users_service.require_deletable_user(user_id, db, if_match=if_match)
    if not core_config.settings.JOBS_ENABLED:
        _deletion_pool.require_capacity()
    job = states.begin(user_id, _Kind.ACCOUNT, conflict=_CONFLICT, owner_id=owner_id)

    try:
        account_security_integration.delete_all_user_sessions(user_id, db)
        sign_up_tokens_integration.revoke_pending_tokens(user_id, db)
        users_crud.stage_deletion_request(user_id, db)
        jasil_audit.stage(
            db,
            users_audit_actions.USER_DELETE,
            target_type="user",
            target_id=str(user_id),
            target_owner_id=str(user_id),
        )
        _dispatch(user_id, states, storage, mail, db, source=users_constants.DELETION_SOURCE_API)
    except BaseException:
        # The deletion never started, so nothing else would finish its claim.
        states.set_status(user_id, _Kind.ACCOUNT, _Status.FAILED)
        raise

    logger.info("Account deletion queued", extra=core_logger.context(user_id=user_id))
    return _status(job, _Status.QUEUED)


def request_deletion_by_administrator(
    user_id: uuid.UUID,
    actor_id: uuid.UUID,
    session_id: uuid.UUID,
    step_up: auth_schema.StepUpVerification,
    step_up_store: account_security_integration.StepUpStore,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    mail: platform_providers.MailProvider,
    db: Session,
    *,
    if_match: str,
) -> users_schema.UserDeletionStatus:
    """Queue the erasure of another user's account on an administrator's request, after their step-up.

    Args:
        user_id: The user to delete.
        actor_id: ID of the administrator making the request.
        session_id: The administrator's session.
        step_up: The administrator's step-up verification.
        step_up_store: Step-up lockout store.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        mail: The platform mail provider, for the in-process pool.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The deletion's initial status, with the id of the job that reads it.

    Raises:
        PermissionDeniedError: If the administrator targets their own account, which needs their account settings.
        StepUpFailedError: If the administrator's step-up verification fails.
        NotFoundError: If the user does not exist.
        PreconditionFailedError: If the user changed since the client read it.
        LastAdministratorError: If the user is the only administrator.
        JobAlreadyRunningError: If a deletion is already pending.
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    users_service.require_other_user(user_id, actor_id, "delete your account")
    account_security_integration.verify_step_up(
        step_up, actor_id, session_id, identity_providers_constants.StepUpAction.ADMIN_USER_DELETE, step_up_store, db
    )
    with core_etag.refuse_stale_write(
        db, "user", lambda: users_crud.get_user_by_id(user_id, db) is not None, "User not found"
    ):
        return request_deletion(user_id, actor_id, states, storage, mail, db, if_match=if_match)


def _dispatch(
    user_id: uuid.UUID,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    mail: platform_providers.MailProvider,
    db: Session,
    *,
    source: str,
) -> None:
    """Commit what the caller staged and hand the erasure to a worker, or to the in-process pool.

    Args:
        user_id: The user to delete.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        mail: The platform mail provider, for the in-process pool.
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
    _deletion_pool.submit(
        run_deletion,
        users_events.DeletionRequestedPayload(user_id=user_id),
        states,
        storage,
        mail,
        first_pass=True,
    )
    logger.debug(
        "Account deletion queued on the in-process pool", extra=core_logger.context(user_id=user_id, source=source)
    )


def durable_pass_seconds() -> float:
    """Return the time budget of one deletion pass on the durable profile.

    Returns:
        A fraction of ``JOBS_LEASE_SECONDS``, never below ``DELETION_PASS_MIN_SECONDS``, so a pass cannot
        outlive the lease it holds.
    """
    lease = core_config.settings.JOBS_LEASE_SECONDS
    return float(max(users_constants.DELETION_PASS_MIN_SECONDS, lease // users_constants.DELETION_PASS_LEASE_FRACTION))


def run_deletion(
    payload: users_events.DeletionRequestedPayload,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    mail: platform_providers.MailProvider,
    *,
    first_pass: bool,
    will_retry: bool = False,
    time_budget: float | None = None,
) -> bool:
    """Erase one account and record the outcome. Blocking; call it from a worker, never a request.

    On its first pass, and only when the sweep has not queued the deletion again, the job first mails the owner
    that the erasure starts (see :func:`_send_deletion_notice`).

    A deletion that raised and will be retried by a durable worker stays ``QUEUED`` with its claim held:
    releasing the claim would let a second deletion start beside the retry. One nothing will retry,
    because there is no worker or this was the last attempt, is ``FAILED`` and its claim is released;
    the account stays deactivated and an administrator deletes it again.

    A pass that spends ``time_budget`` with activities left returns True and leaves the deletion
    ``RUNNING`` with its claim held, so the caller runs it again; the next pass starts from what is left.

    Args:
        payload: Whose account to erase.
        states: Shared store of the deletion's state.
        storage: The platform storage provider.
        mail: The platform mail provider, for the notice to the owner.
        first_pass: Whether this is the job's first delivery, not a retry or a continuation of it.
        will_retry: Whether a durable worker runs this again if it raises.
        time_budget: Seconds after which the activity erasure stops for the caller to continue, or ``None`` to
            run to the end.

    Returns:
        True when activities are left and the caller must run the deletion again; otherwise False.

    Raises:
        Exception: Whatever the deletion raised, when ``will_retry``, so the worker runs it again.
    """
    user_id = payload.user_id
    state = states.get(user_id, _Kind.ACCOUNT)
    if state is None or state.status not in (_Status.QUEUED, _Status.RUNNING):
        logger.debug("Skipped an account deletion that is not pending", extra=core_logger.context(user_id=user_id))
        return False

    if first_pass:
        _send_deletion_notice(user_id, mail)
    states.set_status(user_id, _Kind.ACCOUNT, _Status.RUNNING)
    try:
        activities, activities_left = _erase_activities(user_id, time_budget)
        if activities_left:
            logger.debug("Account deletion pass ended with activities left", extra=core_logger.context(user_id=user_id))
            return True
        _erase_photo(user_id, storage)
        _delete_user_row(user_id)
    except _DeletionCancelledError:
        states.discard(user_id, _Kind.ACCOUNT)
        logger.info("Account deletion cancelled by a reactivation", extra=core_logger.context(user_id=user_id))
        return False
    except Exception as err:
        if will_retry:
            logger.warning(
                "Account deletion failed; it will be retried", exc_info=err, extra=core_logger.context(user_id=user_id)
            )
            states.set_status(user_id, _Kind.ACCOUNT, _Status.QUEUED)
            raise
        logger.error("Account deletion failed", exc_info=err, extra=core_logger.context(user_id=user_id))
        states.set_status(user_id, _Kind.ACCOUNT, _Status.FAILED)
        return False

    users_contributor_registry.erasers().delete_staged_files(user_id, storage)
    users_contributor_registry.erasers().delete_bulk_import_errors(user_id, storage)
    states.set_status(user_id, _Kind.ACCOUNT, _Status.SUCCEEDED)
    logger.info("User deleted", extra=core_logger.context(user_id=user_id, activities=activities))
    return False


def _send_deletion_notice(user_id: uuid.UUID, mail: platform_providers.MailProvider) -> None:
    """Mail the owner, at the address on the row about to be erased, that the account's erasure starts.

    Nothing is sent when the sweep has queued the deletion again, since an earlier pass already sent it, or when
    mail is not configured. The session is closed before the mail call. A mail failure is logged without the
    address and the deletion goes on: the erasure must not wait on mail, and the row, with the address, is gone
    once it finishes.

    Args:
        user_id: The user whose account is erased.
        mail: The platform mail provider.
    """
    with core_database.SessionLocal() as db:
        if users_crud.get_deletion_attempts(user_id, db) != 0 or not server_settings_integration.is_mail_configured(db):
            return
        message = account_security_integration.prepare_account_deletion_email(
            user_id, core_config.settings.ENDURAIN_HOST, db
        )
    if message is None:
        return
    try:
        core_mail.send_email(mail, *message)
    except platform_providers.MailError as err:
        logger.warning(
            "Account deletion notice not sent", extra=core_logger.context(user_id=user_id, error=type(err).__name__)
        )


def _erase_activities(user_id: uuid.UUID, time_budget: float | None) -> tuple[int, bool]:
    """Delete a user's activities one batch per transaction, until none are left or the time budget is spent.

    At least one batch runs, so every pass makes progress.

    Args:
        user_id: The user whose activities to delete.
        time_budget: Seconds after which to stop, or ``None`` to delete them all.

    Returns:
        How many activities were deleted, and whether more may be left.

    Raises:
        _DeletionCancelledError: When the account was reactivated before a batch.
    """
    delete_batch = users_contributor_registry.erasers().delete_activities
    deadline = None if time_budget is None else time.monotonic() + time_budget
    total = 0
    while True:
        with core_database.SessionLocal() as db:
            _require_not_cancelled(user_id, db)
            deleted = delete_batch(user_id, users_constants.DELETION_BATCH_SIZE, db)
            db.commit()
        if not deleted:
            return total, False
        total += deleted
        logger.debug(
            "Erased a batch of a user's activities",
            extra=core_logger.context(user_id=user_id, batch=deleted, total=total),
        )
        if deadline is not None and time.monotonic() >= deadline:
            return total, True


def _require_not_cancelled(user_id: uuid.UUID, db: Session) -> None:
    """Stop the deletion when the account was reactivated; the row stays locked for the caller's transaction.

    Args:
        user_id: The user being deleted.
        db: Database session.

    Raises:
        _DeletionCancelledError: When the account is no longer queued for deletion.
    """
    if users_crud.is_deletion_cancelled(user_id, db):
        raise _DeletionCancelledError


def _erase_photo(user_id: uuid.UUID, storage: platform_providers.StorageProvider) -> None:
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


def _delete_user_row(user_id: uuid.UUID) -> None:
    """Delete the user row, which removes everything else that references it through the database cascade.

    The notifications other users hold that name the user go in the same transaction, so a committed
    deletion leaves none behind.

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
        _stage_user_row_deletion(user_id, db)
        db.commit()
    logger.debug("Deleted the user row", extra=core_logger.context(user_id=user_id))


def _stage_user_row_deletion(user_id: uuid.UUID, db: Session) -> None:
    """Stage the deletion of the user row and of the notifications other users hold that name the user.

    Args:
        user_id: The user to delete.
        db: Database session; the caller commits.
    """
    users_contributor_registry.erasers().delete_notifications(user_id, db)
    users_crud.delete_user(user_id, db)


def stage_unverified_sign_up_purge(
    created_before: datetime, held_user_ids: Sequence[Select[tuple[uuid.UUID]]], limit: int, db: Session
) -> int:
    """Stage the deletion of up to ``limit`` unverified self sign-ups created before ``created_before``.

    An account that never verified its address has no activities, photo or files, so deleting the row, which
    removes the rest through the database cascade, is the whole erasure. Each deletion is audited with the
    system as the actor.

    Args:
        created_before: Only accounts created before this instant qualify.
        held_user_ids: Queries for the ids of the users that must be kept, such as those with a credential.
        limit: The most accounts to delete.
        db: Database session; the caller commits.

    Returns:
        How many accounts were staged for deletion.
    """
    user_ids = users_crud.lock_unverified_sign_ups(created_before, held_user_ids, limit, db)
    for user_id in user_ids:
        _stage_user_row_deletion(user_id, db)
        jasil_audit.stage(
            db,
            users_audit_actions.USER_PURGE,
            target_type="user",
            target_id=str(user_id),
            target_owner_id=str(user_id),
        )
    return len(user_ids)


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
    mail: platform_providers.MailProvider,
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
        mail: The platform mail provider, for the in-process pool.
        clock: The platform clock.

    Returns:
        How many deletions were queued again.
    """
    cutoff = clock.now() - timedelta(seconds=users_constants.DELETION_STALL_AFTER_SECONDS)
    queued = 0
    after_id = None
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
                queued += _requeue(user_id, states, storage, mail)
            except core_local_pool.PoolFullError:
                logger.warning("The deletion pool is full; the sweep stops until its next pass")
                return queued
    if queued:
        logger.info("Queued stalled account deletions again", extra=core_logger.context(count=queued))
    else:
        logger.debug("No stalled account deletions")
    return queued


def _requeue(
    user_id: uuid.UUID,
    states: users_deletion_state_store.UserDeletionStateStore,
    storage: platform_providers.StorageProvider,
    mail: platform_providers.MailProvider,
) -> int:
    """Queue one stalled deletion again unless a job still holds it.

    A failure to queue it is logged and left for the next pass, so one account cannot stop the rest.

    Args:
        user_id: The user to delete.
        states: Shared store of the deletion's state.
        storage: The platform storage provider, for the in-process pool.
        mail: The platform mail provider, for the in-process pool.

    Returns:
        1 when the deletion was queued again, otherwise 0.

    Raises:
        PoolFullError: When there is no durable worker and the in-process pool is full.
    """
    if not core_config.settings.JOBS_ENABLED:
        # Before the claim and the attempt are spent on a deletion nothing can run.
        _deletion_pool.require_capacity()
    try:
        # No request started the sweep, so the account being erased owns the job.
        states.begin(user_id, _Kind.ACCOUNT, conflict=_CONFLICT, owner_id=user_id)
    except core_exceptions.JobAlreadyRunningError:
        logger.debug("A stalled deletion is still held by a job", extra=core_logger.context(user_id=user_id))
        return 0
    try:
        with core_database.SessionLocal() as db:
            attempts = users_crud.record_deletion_attempt(user_id, db)
            if attempts is None:
                # Gone, or an administrator reactivated the account: nothing is left to queue.
                states.set_status(user_id, _Kind.ACCOUNT, _Status.SUCCEEDED)
                return 0
            if attempts == users_constants.DELETION_SWEEP_MAX_ATTEMPTS:
                logger.error(
                    "Account deletion is on its last automatic attempt; an administrator must delete it again if "
                    "this fails",
                    extra=core_logger.context(user_id=user_id, attempts=attempts),
                )
            _dispatch(user_id, states, storage, mail, db, source=users_constants.DELETION_SOURCE_SWEEP)
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
