"""The state machine of a provider sync that is accepted with 202 and runs elsewhere.

Strava and Garmin Connect queue their gear and health syncs and start their account links the same way: a
claim stops the same work being started twice, the work runs on a durable worker or an in-process pool, and
the state a client polls records where it is. The provider-specific parts (what the work is, which errors mean
"the provider refused", what to announce afterwards) stay with the provider and are passed in; the pools, the
claim, the durable job and the bookkeeping live here so a fix to them is made once.
"""

from collections.abc import Callable
from datetime import date, timedelta
from enum import StrEnum

import jasil.event_versioning as platform_event_versioning
from jasil.event_versioning import VersionedPayload
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_Status = core_attempt_state.SyncStatus

#: Link logins or account links one process runs at once, running or queued.
MAX_CONCURRENT_LINKS = 4

#: Syncs the in-process pool may hold, running or queued, when durable jobs are off.
MAX_PENDING_LOCAL_SYNCS = 50

#: Syncs the in-process pool runs at once. Small on purpose: syncs are provider round trips and compete with
#: the request threads.
LOCAL_SYNC_WORKERS = 2

#: Longest activity range one request may ask for; a longer history is fetched in several requests.
MAX_ACTIVITIES_RANGE_DAYS = 366


def sync_pool(name: str) -> core_local_pool.BoundedPool:
    """Build a provider's in-process sync pool, which runs its syncs when durable jobs are off.

    Args:
        name: The pool's thread-name prefix.

    Returns:
        The pool.
    """
    return core_local_pool.BoundedPool(name, workers=LOCAL_SYNC_WORKERS, max_pending=MAX_PENDING_LOCAL_SYNCS)


def link_pool(name: str) -> core_local_pool.BoundedPool:
    """Build a provider's link pool, which runs account links off the request threadpool.

    A link past its capacity is refused rather than queued: a link holds what the user just handed over (a
    password, a one-time code) only in this process's memory, so it is never a durable job and never waits.

    Args:
        name: The pool's thread-name prefix.

    Returns:
        The pool.
    """
    return core_local_pool.BoundedPool(name, workers=MAX_CONCURRENT_LINKS, max_pending=MAX_CONCURRENT_LINKS)


def validate_range(start_date: date, end_date: date, max_days: int, today: date) -> None:
    """Refuse a reversed date range, a future one, or one longer than ``max_days``.

    Args:
        start_date: First day of the range.
        end_date: Last day of the range.
        max_days: Longest range allowed.
        today: The user's current calendar date.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date``, ``end_date`` is in the future or
            the range is too long.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")
    if end_date > today:
        raise core_exceptions.InvalidInputError("end_date must not be in the future")
    if end_date - start_date >= timedelta(days=max_days):
        raise core_exceptions.InvalidInputError(f"The date range must not exceed {max_days} days")


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


def start_claimed(
    claim: Callable[[], bool], conflict: str, start: Callable[[], None], release: Callable[[], None]
) -> None:
    """Take a claim and start the work it guards, giving the claim back when the work never started.

    Args:
        claim: Takes the claim; False when the work is already pending.
        conflict: The detail of the error for a claim already taken.
        start: Hands the work to a worker or a pool.
        release: Gives the claim back.

    Raises:
        ConflictError: When the claim is already taken.
    """
    if not claim():
        raise core_exceptions.ConflictError(conflict)
    try:
        start()
    except BaseException:
        # The work never started, so nothing else would release its claim.
        release()
        raise


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
    start_claimed(
        lambda: states.begin(user_id, kind),
        f"A {label} {kind.value} sync is already in progress",
        publish if durable else submit,
        lambda: states.set_status(user_id, kind, _Status.FAILED),
    )


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
        logger.error(
            "A <label> sync was dead-lettered", extra=core_logger.context(label=label, user_id=user_id, kind=kind)
        )


def register_sync_job[PayloadT: VersionedPayload](
    registry: JobHandlerRegistry,
    event_type: str,
    subscriber_id: str,
    payload_type: type[PayloadT],
    *,
    run: Callable[[PayloadT, bool], None],
    close: Callable[[PayloadT], None],
) -> None:
    """Register a provider's queued sync as a durable job, with the dead-letter hook that closes it.

    Args:
        registry: The durable-handler registry to register on.
        event_type: The event that requests the sync.
        subscriber_id: The durable subscriber's stable id.
        payload_type: The event's payload model.
        run: Runs the sync; called with the payload and whether a durable worker runs it again if it raises.
        close: Closes a sync the runner gave up on; called with the payload.
    """

    def handle(event: Event) -> None:
        """Run one queued sync.

        Args:
            event: The event that requested it.
        """
        run(platform_event_versioning.parse_payload(payload_type, event), not event.is_last_attempt)
        logger.debug("A sync job finished", extra=core_logger.context(subscriber_id=subscriber_id))

    def on_dead_letter(event: Event, error: str | None) -> None:
        """Close a sync the runner gave up on.

        Args:
            event: The event that requested it.
            error: What the runner recorded, which the sync's own log line already carries.
        """
        close(platform_event_versioning.parse_payload(payload_type, event))

    registry.register(event_type, subscriber_id, handle, on_dead_letter=on_dead_letter)
