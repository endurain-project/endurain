"""Tests for processing_jobs CRUD — enqueue/claim/complete/fail/reap on real SQLite."""

from datetime import UTC, datetime, timedelta

import pytest

import core.jobs.crud as jobs_crud
import core.platform.events as platform_events
from core.jobs.models import ProcessingJob
from tests._helpers.db import create_sqlite_session

_NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)


def _naive(moment):
    # SQLite stores DateTime(timezone=True) as naive; compare wall-clock instants.
    return moment.replace(tzinfo=None) if moment is not None else None


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()
    session.bind.dispose()  # StaticPool keeps one connection; dispose to avoid ResourceWarning


def _event(event_id="e1", event_type="activity.created", metadata=None):
    return platform_events.Event(
        event_id=event_id,
        event_type=event_type,
        source="api:test",
        timestamp="2026-07-14T12:00:00+00:00",
        payload={"activity_id": 42},
        metadata=metadata if metadata is not None else {"activity_id": 42},
        retry_count=0,
    )


def _enqueue(db, event=None, subscriber_id="sub.a", *, max_attempts=3, now=_NOW, available_at=None):
    return jobs_crud.enqueue_job(
        event or _event(),
        subscriber_id,
        max_attempts=max_attempts,
        now=now,
        db=db,
        available_at=available_at,
    )


class TestEnqueue:
    def test_inserts_pending_job(self, db):
        job = _enqueue(db)
        assert job is not None
        assert job.status == "pending"
        assert job.event_id == "e1"
        assert job.subscriber_id == "sub.a"
        assert job.attempts == 0
        assert job.max_attempts == 3
        assert job.payload == {"activity_id": 42}
        assert job.job_metadata == {"activity_id": 42}

    def test_empty_metadata_stored_as_null(self, db):
        job = _enqueue(db, _event(metadata={}))
        assert job is not None
        assert job.job_metadata is None

    def test_duplicate_event_subscriber_is_noop(self, db):
        first = _enqueue(db)
        second = _enqueue(db)
        assert first is not None
        assert second is None
        assert db.query(ProcessingJob).count() == 1

    def test_same_event_different_subscriber_creates_two(self, db):
        _enqueue(db, subscriber_id="sub.a")
        _enqueue(db, subscriber_id="sub.b")
        assert db.query(ProcessingJob).count() == 2


class TestClaim:
    def test_claims_due_job_and_takes_lease(self, db):
        _enqueue(db)
        claimed = jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        assert len(claimed) == 1
        job = claimed[0]
        assert job.status == "claimed"
        assert job.attempts == 1
        assert job.locked_by == "w1"
        assert _naive(job.lease_expires_at) == _naive(_NOW + timedelta(seconds=300))

    def test_nothing_due_returns_empty(self, db):
        assert jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db) == []

    def test_future_available_at_is_not_claimed(self, db):
        _enqueue(db, available_at=_NOW + timedelta(hours=1))
        assert jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db) == []

    def test_respects_limit_and_orders_by_available_at(self, db):
        _enqueue(db, _event("older"), subscriber_id="s1", available_at=_NOW - timedelta(minutes=3))
        _enqueue(db, _event("middle"), subscriber_id="s2", available_at=_NOW - timedelta(minutes=2))
        _enqueue(db, _event("newer"), subscriber_id="s3", available_at=_NOW - timedelta(minutes=1))
        claimed = jobs_crud.claim_jobs(worker_id="w1", limit=2, lease_seconds=300, now=_NOW, db=db)
        assert [job.event_id for job in claimed] == ["older", "middle"]

    def test_claimed_job_is_not_reclaimed_by_second_worker(self, db):
        _enqueue(db)
        jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        assert jobs_crud.claim_jobs(worker_id="w2", limit=10, lease_seconds=300, now=_NOW, db=db) == []


class TestMarkCompleted:
    def test_marks_completed_and_clears_lease(self, db):
        _enqueue(db)
        claimed = jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        jobs_crud.mark_job_completed(claimed[0].id, now=_NOW, db=db)
        job = jobs_crud.get_job(claimed[0].id, db)
        assert job is not None
        assert job.status == "completed"
        assert _naive(job.completed_at) == _naive(_NOW)
        assert job.locked_by is None
        assert job.lease_expires_at is None


class TestMarkFailed:
    def test_reschedules_with_backoff_when_attempts_remain(self, db):
        _enqueue(db, max_attempts=3)
        claimed = jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        status = jobs_crud.mark_job_failed(claimed[0].id, "boom", base_seconds=5.0, max_seconds=3600.0, now=_NOW, db=db)
        job = jobs_crud.get_job(claimed[0].id, db)
        assert status == "pending"
        assert job is not None
        assert job.status == "pending"
        assert job.last_error == "boom"
        # attempts == 1 -> first retry waits base_seconds (5s), with equal jitter
        # applied: the delay lands in [50%, 100%] of 5s, i.e. between 2.5s and 5s.
        assert _naive(_NOW + timedelta(seconds=2.5)) <= _naive(job.available_at) <= _naive(_NOW + timedelta(seconds=5))
        assert job.locked_by is None

    def test_dead_letters_when_attempts_exhausted(self, db):
        _enqueue(db, max_attempts=1)
        claimed = jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        status = jobs_crud.mark_job_failed(claimed[0].id, "boom", base_seconds=5.0, max_seconds=3600.0, now=_NOW, db=db)
        job = jobs_crud.get_job(claimed[0].id, db)
        assert status == "dead_letter"
        assert job is not None
        assert job.status == "dead_letter"
        assert _naive(job.completed_at) == _naive(_NOW)

    def test_truncates_long_error(self, db):
        _enqueue(db, max_attempts=3)
        claimed = jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        jobs_crud.mark_job_failed(claimed[0].id, "x" * 5000, base_seconds=5.0, max_seconds=3600.0, now=_NOW, db=db)
        job = jobs_crud.get_job(claimed[0].id, db)
        assert job is not None
        assert job.last_error is not None
        assert len(job.last_error) == 4000

    def test_missing_job_returns_empty_status(self, db):
        assert jobs_crud.mark_job_failed("nope", "boom", base_seconds=5.0, max_seconds=3600.0, now=_NOW, db=db) == ""


class TestReclaimExpiredLeases:
    def test_requeues_expired_lease_with_attempts_remaining(self, db):
        _enqueue(db, max_attempts=3)
        jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        later = _NOW + timedelta(seconds=301)
        reclaimed = jobs_crud.reclaim_expired_leases(now=later, db=db)
        assert reclaimed == 1
        job = db.query(ProcessingJob).one()
        assert job.status == "pending"
        assert _naive(job.available_at) == _naive(later)
        assert job.locked_by is None

    def test_dead_letters_expired_lease_when_exhausted(self, db):
        _enqueue(db, max_attempts=1)
        jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        later = _NOW + timedelta(seconds=301)
        reclaimed = jobs_crud.reclaim_expired_leases(now=later, db=db)
        assert reclaimed == 1
        assert db.query(ProcessingJob).one().status == "dead_letter"

    def test_ignores_unexpired_lease(self, db):
        _enqueue(db)
        jobs_crud.claim_jobs(worker_id="w1", limit=10, lease_seconds=300, now=_NOW, db=db)
        within = _NOW + timedelta(seconds=100)
        assert jobs_crud.reclaim_expired_leases(now=within, db=db) == 0
        assert db.query(ProcessingJob).one().status == "claimed"

    def test_nothing_to_reclaim_returns_zero(self, db):
        assert jobs_crud.reclaim_expired_leases(now=_NOW, db=db) == 0
