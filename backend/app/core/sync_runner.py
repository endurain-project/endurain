"""The state machine of a provider sync that is accepted with 202 and runs elsewhere.

Strava and Garmin Connect queue their gear and health syncs the same way: a claim stops the same sync being
queued twice, the work runs on a durable worker or an in-process pool, and the state a client polls records
where it is. The provider-specific parts (what the work is, which errors mean "the provider refused", what to
announce afterwards) stay with the provider and are passed in; the bookkeeping lives here so a fix to it is
made once.
"""

from collections.abc import Callable
from enum import StrEnum

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_Status = core_attempt_state.SyncStatus

#: Link logins or account links one process runs at once, running or queued.
MAX_CONCURRENT_LINKS = 4

#: Syncs the in-process pool may hold, running or queued, when durable jobs are off.
MAX_PENDING_LOCAL_SYNCS = 50

#: Longest activity range one request may ask for; a longer history is fetched in several requests.
MAX_ACTIVITIES_RANGE_DAYS = 366


def run_recorded(
    states: core_attempt_state.SyncStateStore,
    user_id: int,
    kind: StrEnum,
    work: Callable[[], bool],
    *,
    will_retry: bool,
    refusals: tuple[type[Exception], ...] = (),
    on_refused: Callable[[Exception], None] | None = None,
) -> bool | None:
    """Run the work of a queued sync and record how it ended. Blocking; call it from a worker.

    A provider refusal (``refusals``) is recorded as failed and not raised, because a retry would meet the same
    answer. Any other error leaves the sync ``QUEUED`` with its claim held when a durable worker will run it
    again, since releasing the claim would let a second sync start beside the retry; with nothing to retry it,
    the sync is ``FAILED`` and the claim is released. The error is raised either way.

    Args:
        states: Shared store of the sync's state.
        user_id: The user being synced.
        kind: What the sync does.
        work: The sync itself; returns whether it did anything.
        will_retry: Whether a durable worker runs this again if it raises.
        refusals: Errors that mean the provider refused the sync.
        on_refused: Called with a refusal before it is recorded, for the provider's own bookkeeping.

    Returns:
        True when the sync finished and did something, False when it finished with nothing to do, None when
        the provider refused it.

    Raises:
        Exception: Whatever the work raised other than a refusal, after the state was recorded.
    """
    states.set_status(user_id, kind, _Status.RUNNING)
    try:
        synced = work()
    except refusals as err:
        if on_refused is not None:
            on_refused(err)
        logger.warning("The provider refused the sync", extra=core_logger.context(user_id=user_id, kind=kind))
        states.set_status(user_id, kind, _Status.FAILED)
        return None
    except Exception:
        states.set_status(user_id, kind, _Status.QUEUED if will_retry else _Status.FAILED)
        raise
    states.set_status(user_id, kind, _Status.COMPLETED if synced else _Status.FAILED)
    return synced


def queue_sync(
    states: core_attempt_state.SyncStateStore,
    user_id: int,
    kind: StrEnum,
    label: str,
    *,
    durable: bool,
    publish: Callable[[], None],
    submit: Callable[[], None],
) -> None:
    """Claim a sync and hand it to a durable worker, or to the in-process pool without durable jobs.

    Args:
        states: Shared store of the sync's state.
        user_id: The user to sync.
        kind: What the sync does.
        label: The provider's name, for messages.
        durable: Whether a durable worker takes the sync.
        publish: Stages the work for a durable worker.
        submit: Submits the work to the in-process pool.

    Raises:
        ConflictError: When a sync of this kind is already pending for the user.
    """
    if not states.begin(user_id, kind):
        raise core_exceptions.ConflictError(f"A {label} {kind.value} sync is already in progress")
    try:
        if durable:
            publish()
        else:
            submit()
    except BaseException:
        # The sync never started, so nothing else would finish its claim.
        states.set_status(user_id, kind, _Status.FAILED)
        raise


def read_state(
    states: core_attempt_state.SyncStateStore, user_id: int, kind: StrEnum, label: str
) -> core_attempt_state.SyncState:
    """Read where a user's sync is.

    Args:
        states: Shared store of the sync's state.
        user_id: The user being synced.
        kind: What the sync does.
        label: The provider's name, for the message.

    Returns:
        The recorded state.

    Raises:
        NotFoundError: When no sync is recorded or it has expired.
    """
    state = states.get(user_id, kind)
    if state is None:
        raise core_exceptions.NotFoundError(f"No {label} {kind.value} sync recorded")
    return state


def close_dead_lettered(states: core_attempt_state.SyncStateStore, user_id: int, kind: StrEnum, label: str) -> None:
    """Close a sync the runner gave up on, so the user can queue another.

    Runs however the last attempt ended, including a lease that expired or a worker that died. A sync that
    already finished, or whose state has expired, is left as it is, and so is a newer sync that took its claim.

    Args:
        states: Shared store of the sync's state.
        user_id: The user whose sync was dead-lettered.
        kind: What the sync did.
        label: The provider's name, for the log.
    """
    if states.close_pending(user_id, kind):
        logger.error(f"A {label} sync was dead-lettered", extra=core_logger.context(user_id=user_id, kind=kind))
