"""Overlapping Strava-activity deletions of one user, on PostgreSQL.

``delete_all_strava_activities_for_user`` locks the rows it selects in id order, so a second session that selects the
same rows waits, then finds them gone: each activity is deleted once and recorded once, and two overlapping bulk
deletes never deadlock. The first test holds the rows in one session and starts the second on a thread; the others race
whole delete loops on two threads.
"""

import threading
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import modules.activities.activity.crud as activity_crud
import modules.activities.activity.models as activity_models
from tests._factories.activities import make_activity_at
from tests._helpers.concurrency import Worker, wait_until_a_session_waits_for_a_lock

_START = datetime(2026, 3, 1, 8, tzinfo=UTC)


@pytest.fixture
def synced(arrange, owner) -> list:
    """Ids of five of the owner's Strava-synced activities."""
    return arrange(
        lambda db: [
            make_activity_at(db, owner.id, _START + timedelta(days=n), strava_activity_id=1000 + n).id for n in range(5)
        ]
    )


@pytest.fixture
def kept(arrange, owner, other) -> list:
    """Ids of what a Strava deletion must leave: two of the owner's own activities and another user's synced one."""
    return arrange(
        lambda db: [
            make_activity_at(db, owner.id, _START + timedelta(days=10)).id,
            make_activity_at(db, owner.id, _START + timedelta(days=11)).id,
            make_activity_at(db, other.id, _START, strava_activity_id=1).id,
        ]
    )


def _remaining(committed_sessions) -> set:
    with committed_sessions() as db:
        return set(db.scalars(select(activity_models.Activity.id)))


def _logged(committed_sessions) -> Counter:
    with committed_sessions() as db:
        return Counter(db.scalars(select(activity_models.ActivityDeletion.record_id)))


def _delete_until_done(committed_sessions, user_id, limit: int, barrier: threading.Barrier) -> list:
    """Delete in committed batches until fewer than ``limit`` come back, as a caller of the batch does."""
    barrier.wait()
    deleted: list = []
    while True:
        with committed_sessions() as db:
            batch = activity_crud.delete_all_strava_activities_for_user(user_id, db, limit=limit)
            db.commit()
        deleted += batch
        if len(batch) < limit:
            return deleted


class TestStravaDeletionOverlap:
    def test_a_second_delete_waits_for_the_first_and_then_finds_nothing_to_delete(
        self, committed_sessions, owner, synced, kept
    ):
        with committed_sessions() as first:
            first_deleted = activity_crud.delete_all_strava_activities_for_user(owner.id, first, limit=10)

            def second_delete() -> list:
                with committed_sessions() as db:
                    deleted = activity_crud.delete_all_strava_activities_for_user(owner.id, db, limit=10)
                    db.commit()
                return deleted

            worker = Worker(second_delete)
            wait_until_a_session_waits_for_a_lock(committed_sessions)
            first.commit()
            worker.join()

        assert worker.error is None
        assert sorted(first_deleted) == sorted(synced)
        assert worker.result == []
        assert _remaining(committed_sessions) == set(kept)
        assert _logged(committed_sessions) == Counter(synced)

    def test_two_overlapping_delete_loops_delete_and_log_each_activity_once(
        self, committed_sessions, owner, synced, kept
    ):
        barrier = threading.Barrier(2)
        workers = [Worker(lambda: _delete_until_done(committed_sessions, owner.id, 2, barrier)) for _ in range(2)]
        for worker in workers:
            worker.join()

        assert [worker.error for worker in workers] == [None, None]
        deleted = Counter(workers[0].result + workers[1].result)
        assert deleted == Counter(synced)
        assert _remaining(committed_sessions) == set(kept)
        assert _logged(committed_sessions) == Counter(synced)

    def test_a_strava_delete_loop_and_an_account_deletion_loop_finish_without_a_deadlock(
        self, committed_sessions, owner, synced, kept
    ):
        barrier = threading.Barrier(2)

        def delete_account_batches() -> list:
            barrier.wait()
            deleted: list = []
            while True:
                with committed_sessions() as db:
                    batch = activity_crud.delete_activities_batch_for_user(owner.id, 2, db)
                    db.commit()
                deleted += batch
                if not batch:
                    return deleted

        strava = Worker(lambda: _delete_until_done(committed_sessions, owner.id, 2, barrier))
        account = Worker(delete_account_batches)
        strava.join()
        account.join()

        assert (strava.error, account.error) == (None, None)
        owners_activities = set(synced) | set(kept[:2])
        assert Counter(strava.result + account.result) == Counter(owners_activities)
        assert _remaining(committed_sessions) == {kept[2]}
        assert _logged(committed_sessions) == Counter(owners_activities)
