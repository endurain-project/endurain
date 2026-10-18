"""Concurrent follow, accept and unfollow against real PostgreSQL.

The service pre-checks and the CRUD stages, but the guarantees that matter
under several replicas are the unique pair, the conditional ``UPDATE`` and the
check constraints, which only separate connections can exercise.
"""

import threading
from collections.abc import Callable

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.followers.constants as followers_constants
import modules.followers.crud as followers_crud
import modules.followers.models as followers_models
from tests._helpers.db import ensure_user

_THREADS = 6


@pytest.fixture
def factory(pg_factory):
    for user_id in (1, 2, 3):
        ensure_user(pg_factory, user_id)
    return pg_factory


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


def _status(factory, follower_id: int, followee_id: int) -> str | None:
    with factory() as db:
        return db.scalar(
            select(followers_models.Follower.status).where(
                followers_models.Follower.follower_id == follower_id,
                followers_models.Follower.followee_id == followee_id,
            )
        )


def _add_follow(factory, follower_id: int, followee_id: int, status: followers_constants.FollowStatus) -> None:
    with factory() as db:
        db.add(followers_models.Follower(follower_id=follower_id, followee_id=followee_id, status=status.value))
        db.commit()


def test_concurrent_follow_requests_create_one_row_and_conflict_for_the_rest(factory):
    outcomes = _race(factory, lambda db: followers_crud.create_follower(1, 2, db))

    conflicts = [o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]
    assert len(outcomes) == _THREADS
    assert len(conflicts) == _THREADS - 1
    assert _status(factory, 1, 2) == "pending"


def test_following_a_user_that_does_not_exist_is_not_found_rather_than_a_conflict(factory):
    with factory() as db, pytest.raises(core_exceptions.NotFoundError):
        followers_crud.create_follower(1, 999, db)


def test_concurrent_accepts_have_exactly_one_winner(factory):
    _add_follow(factory, 1, 2, followers_constants.FollowStatus.PENDING)

    outcomes = _race(factory, lambda db: followers_crud.accept_follower(2, 1, db))

    not_found = [o for o in outcomes if isinstance(o, core_exceptions.NotFoundError)]
    assert len(outcomes) == _THREADS
    assert len(not_found) == _THREADS - 1
    assert _status(factory, 1, 2) == "accepted"


def test_an_accept_racing_a_reject_leaves_a_consistent_row(factory):
    """Whichever commits first wins, and the other reports not-found instead of resurrecting the row."""
    _add_follow(factory, 1, 2, followers_constants.FollowStatus.PENDING)
    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}

    def accept() -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes["accept"] = followers_crud.accept_follower(2, 1, db)
                db.commit()
            except core_exceptions.NotFoundError as err:
                db.rollback()
                outcomes["accept"] = err

    def reject() -> None:
        barrier.wait()
        with factory() as db:
            try:
                followers_crud.delete_follower(1, 2, db, status=followers_constants.FollowStatus.PENDING)
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
    assert _status(factory, 1, 2) == ("accepted" if accepted else None)


def test_a_reject_cannot_remove_an_accepted_follower(factory):
    _add_follow(factory, 1, 2, followers_constants.FollowStatus.ACCEPTED)

    with factory() as db, pytest.raises(core_exceptions.NotFoundError):
        followers_crud.delete_follower(1, 2, db, status=followers_constants.FollowStatus.PENDING)

    assert _status(factory, 1, 2) == "accepted"


def test_the_database_refuses_a_self_follow(factory):
    with factory() as db:
        db.add(followers_models.Follower(follower_id=1, followee_id=1, status="pending"))
        with pytest.raises(IntegrityError):
            db.flush()


def test_the_database_refuses_an_unknown_status(factory):
    with factory() as db:
        db.add(followers_models.Follower(follower_id=1, followee_id=2, status="blocked"))
        with pytest.raises(IntegrityError):
            db.flush()


def test_the_opposite_directions_are_independent_relationships(factory):
    _add_follow(factory, 1, 2, followers_constants.FollowStatus.PENDING)
    _add_follow(factory, 2, 1, followers_constants.FollowStatus.PENDING)

    with factory() as db:
        assert db.execute(text("SELECT count(*) FROM followers")).scalar_one() == 2
