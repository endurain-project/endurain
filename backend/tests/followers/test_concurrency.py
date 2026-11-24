"""Concurrent follow, accept, decline and block against real PostgreSQL.

The service pre-checks and the CRUD stages, but the guarantees that matter under several replicas are the unique
pair, the conditional ``UPDATE``, the advisory locks that serialise the caps and the blocks, which only separate
connections can exercise.
"""

import threading
import time
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError

import core.exceptions as core_exceptions
import modules.followers.constants as followers_constants
import modules.followers.crud as followers_crud
import modules.followers.models as followers_models
import modules.followers.service as followers_service
from tests._factories.followers import make_follow
from tests._factories.users import make_user

_THREADS = 6


@pytest.fixture
def people(committed_sessions):
    """Eight committed users: the first two are the pair the tests race over, the rest are extra."""
    with committed_sessions() as db:
        users = [make_user(db).id for _ in range(_THREADS + 2)]
        db.commit()
    return users


@pytest.fixture
def factory(committed_sessions):
    return committed_sessions


def _race(factory, work: Callable, count: int = _THREADS) -> list:
    """Run ``work(db)`` on ``count`` sessions released together; return each outcome."""
    barrier = threading.Barrier(count)
    outcomes: list = []

    def run() -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes.append(work(db))
                db.commit()
            except Exception as err:
                db.rollback()
                outcomes.append(err)

    threads = [threading.Thread(target=run) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    return outcomes


def _wait_until_a_session_waits_for_a_lock(factory, timeout: float = 10.0) -> None:
    """Block until another session of this database is waiting on a lock, so a test acts at that exact point."""
    deadline = time.monotonic() + timeout
    with factory() as probe:
        while time.monotonic() < deadline:
            waiting = probe.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                )
            )
            if waiting:
                return
            # PostgreSQL reads pg_stat_activity once per transaction, so each poll needs a transaction of its own.
            probe.rollback()
            # A poll of the database's own state, not a wait for time to pass: it ends the moment the lock wait shows.
            threading.Event().wait(0.02)
    raise AssertionError("no session waited for a lock")


def _status(factory, follower_id: uuid.UUID, followee_id: uuid.UUID) -> str | None:
    with factory() as db:
        return db.scalar(
            select(followers_models.Follower.status).where(
                followers_models.Follower.follower_id == follower_id,
                followers_models.Follower.followee_id == followee_id,
            )
        )


def _add_follow(factory, follower_id: uuid.UUID, followee_id: uuid.UUID, *, accepted: bool) -> None:
    with factory() as db:
        make_follow(db, follower_id, followee_id, accepted=accepted)
        db.commit()


def test_concurrent_follow_requests_create_one_row_and_conflict_for_the_rest(factory, people):
    first, second = people[:2]

    outcomes = _race(factory, lambda db: followers_crud.create_follower(first, second, db))

    conflicts = [o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]
    assert len(outcomes) == _THREADS
    assert len(conflicts) == _THREADS - 1
    assert _status(factory, first, second) == "pending"


def test_a_follow_that_loses_the_race_after_its_pre_check_is_a_conflict(factory, people):
    """The pre-check passes while the other follow is uncommitted; the unique pair then refuses the insert."""
    first, second = people[:2]
    outcome: list = []

    def follow_again() -> None:
        with factory() as db:
            try:
                outcome.append(followers_crud.create_follower(first, second, db))
            except Exception as err:
                db.rollback()
                outcome.append(err)

    with factory() as winner:
        followers_crud.create_follower(first, second, winner)
        thread = threading.Thread(target=follow_again)
        thread.start()
        _wait_until_a_session_waits_for_a_lock(factory)
        winner.commit()
    thread.join(timeout=20)

    assert len(outcome) == 1
    assert isinstance(outcome[0], core_exceptions.ConflictError)
    assert _status(factory, first, second) == "pending"


def test_a_block_that_loses_the_race_after_its_pre_check_reports_the_existing_one(factory, people):
    """The pre-check passes while the other block is uncommitted; the unique pair then refuses the insert."""
    blocker, blocked = people[:2]
    outcome: list = []

    def block_again() -> None:
        with factory() as db:
            try:
                outcome.append(followers_crud.create_block(blocker, blocked, db))
                db.commit()
            except Exception as err:
                db.rollback()
                outcome.append(err)

    with factory() as winner:
        assert followers_crud.create_block(blocker, blocked, winner) is True
        thread = threading.Thread(target=block_again)
        thread.start()
        _wait_until_a_session_waits_for_a_lock(factory)
        winner.commit()
    thread.join(timeout=20)

    assert outcome == [False]
    with factory() as db:
        assert followers_crud.list_blocked_user_ids(blocker, db) == [blocked]


def test_blocking_a_user_that_does_not_exist_is_refused_by_the_database(factory, people):
    with factory() as db, pytest.raises(IntegrityError, match="follower_blocks_blocked_id_fkey"):
        followers_crud.create_block(people[0], uuid.uuid4(), db)


def test_following_a_user_that_does_not_exist_is_not_found_rather_than_a_conflict(factory, people):
    with factory() as db, pytest.raises(core_exceptions.NotFoundError):
        followers_crud.create_follower(people[0], uuid.uuid4(), db)


def test_concurrent_accepts_have_exactly_one_winner(factory, people):
    first, second = people[:2]
    _add_follow(factory, first, second, accepted=False)

    outcomes = _race(factory, lambda db: followers_crud.accept_follower(second, first, db))

    not_found = [o for o in outcomes if isinstance(o, core_exceptions.NotFoundError)]
    assert len(outcomes) == _THREADS
    assert len(not_found) == _THREADS - 1
    assert _status(factory, first, second) == "accepted"


def test_an_accept_racing_a_reject_leaves_a_consistent_row(factory, people):
    """Whichever commits first wins, and the other reports not-found instead of resurrecting the row."""
    first, second = people[:2]
    _add_follow(factory, first, second, accepted=False)
    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def accept() -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes["accept"] = followers_crud.accept_follower(second, first, db)
                db.commit()
            except core_exceptions.NotFoundError as err:
                db.rollback()
                outcomes["accept"] = err

    def reject() -> None:
        barrier.wait()
        with factory() as db:
            try:
                followers_crud.delete_follower(first, second, db, status=followers_constants.FollowStatus.PENDING)
                db.commit()
                outcomes["reject"] = "deleted"
            except core_exceptions.NotFoundError as err:
                db.rollback()
                outcomes["reject"] = err

    threads = [threading.Thread(target=accept), threading.Thread(target=reject)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    accepted = not isinstance(outcomes["accept"], Exception)
    rejected = outcomes["reject"] == "deleted"
    # A reject scoped to ``pending`` cannot delete an accepted row, so exactly one side wins.
    assert accepted != rejected
    assert _status(factory, first, second) == ("accepted" if accepted else None)


def test_concurrent_follow_requests_cannot_exceed_the_pending_cap(factory, people, monkeypatch):
    monkeypatch.setattr(followers_constants, "MAX_PENDING_REQUESTS", 2)
    target = people[0]
    requesters = iter(people[2:])
    lock = threading.Lock()

    def follow(db):
        with lock:
            requester = next(requesters)
        return followers_service.follow_user(requester, target, db)

    outcomes = _race(factory, follow)

    with factory() as db:
        pending = followers_crud.count_pending_requests_for_user_id(target, db)
    assert pending == 2
    assert len([o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]) == _THREADS - 2


def test_concurrent_accepts_cannot_exceed_the_followee_cap(factory, people, monkeypatch):
    monkeypatch.setattr(followers_constants, "MAX_ACCEPTED_FOLLOWEES", 2)
    follower = people[0]
    followees = people[2:]
    for followee in followees:
        _add_follow(factory, follower, followee, accepted=False)
    accepters = iter(followees)
    lock = threading.Lock()

    def accept(db):
        with lock:
            followee = next(accepters)
        return followers_service.accept_follow_request(followee, follower, db)

    outcomes = _race(factory, accept)

    with factory() as db:
        accepted = followers_crud.count_following_by_user_id(follower, db, accepted_only=True)
    assert accepted == 2
    assert len([o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]) == _THREADS - 2


class TestAdvisoryLocks:
    """A lock is held until its transaction ends; a second writer waits only when user and namespace both match."""

    @staticmethod
    def _blocks(factory, take_first: Callable, take_second: Callable) -> bool:
        """Whether the second writer is refused within one second while the first holds its lock."""
        with factory() as holder, factory() as waiter:
            take_first(holder)
            waiter.execute(text("SET LOCAL lock_timeout = '1s'"))
            try:
                take_second(waiter)
            except OperationalError:
                return True
            return False

    def test_a_second_pending_writer_for_the_same_user_waits(self, factory, people):
        user = people[0]

        assert self._blocks(
            factory,
            lambda db: followers_crud.lock_pending_requests(user, db),
            lambda db: followers_crud.lock_pending_requests(user, db),
        )

    def test_the_lock_is_released_when_the_transaction_commits(self, factory, people):
        user = people[0]
        with factory() as holder, factory() as waiter:
            followers_crud.lock_pending_requests(user, holder)
            holder.commit()

            waiter.execute(text("SET LOCAL lock_timeout = '1s'"))
            followers_crud.lock_pending_requests(user, waiter)

    def test_another_user_is_not_held_up(self, factory, people):
        assert not self._blocks(
            factory,
            lambda db: followers_crud.lock_pending_requests(people[0], db),
            lambda db: followers_crud.lock_pending_requests(people[1], db),
        )

    def test_the_accepted_followee_lock_is_apart_from_the_pending_one(self, factory, people):
        user = people[0]

        assert not self._blocks(
            factory,
            lambda db: followers_crud.lock_pending_requests(user, db),
            lambda db: followers_crud.lock_accepted_followees(user, db),
        )
        assert self._blocks(
            factory,
            lambda db: followers_crud.lock_accepted_followees(user, db),
            lambda db: followers_crud.lock_accepted_followees(user, db),
        )


def _follow_and_block_interleaved(factory, monkeypatch, requester: uuid.UUID, blocker: uuid.UUID, target: uuid.UUID):
    """Hold the follow between its last block check and its insert until the block ran or 2 s passed."""
    checked = threading.Event()
    blocked = threading.Event()
    real_is_blocked = followers_crud.is_blocked
    checks = []

    def is_blocked(blocker_id, blocked_id, db):
        result = real_is_blocked(blocker_id, blocked_id, db)
        if threading.current_thread().name == "follow":
            checks.append(blocker_id)
        # The follow's second check is its last one: pause there so the block commits before the insert.
        if threading.current_thread().name == "follow" and len(checks) == 2:
            checked.set()
            blocked.wait(timeout=2)
        return result

    monkeypatch.setattr(followers_service.followers_crud, "is_blocked", is_blocked)
    outcomes: dict[str, object] = {}

    def follow() -> None:
        with factory() as db:
            try:
                outcomes["follow"] = followers_service.follow_user(requester, target, db)
            except Exception as err:
                db.rollback()
                outcomes["follow"] = err

    def block() -> None:
        checked.wait(timeout=5)
        with factory() as db:
            followers_service.block_user(blocker, target if blocker == requester else requester, db)
        blocked.set()

    threads = [threading.Thread(target=follow, name="follow"), threading.Thread(target=block, name="block")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    return outcomes


def test_a_block_racing_a_follow_leaves_no_pending_request_from_the_blocked_user(factory, people, monkeypatch):
    requester, blocker = people[:2]
    _follow_and_block_interleaved(factory, monkeypatch, requester=requester, blocker=blocker, target=blocker)

    assert _status(factory, requester, blocker) is None


def test_the_requester_blocking_the_target_during_their_own_follow_leaves_no_pending_request(
    factory, people, monkeypatch
):
    requester, target = people[:2]
    _follow_and_block_interleaved(factory, monkeypatch, requester=requester, blocker=requester, target=target)

    assert _status(factory, requester, target) is None
