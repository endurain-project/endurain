"""Tests for the durable-jobs summary and replay CRUD (real SQLite)."""

from datetime import UTC, datetime, timedelta

import pytest

import infra.jobs.crud as jobs_crud
from infra.jobs.models import ProcessingJob
from tests._helpers.db import create_sqlite_session


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()
    session.bind.dispose()  # StaticPool keeps one connection; dispose to avoid ResourceWarning


def _insert_job(db, *, job_id, subscriber_id, status, event_type="activity.created", attempts=1, updated_at=None):
    now = datetime.now(UTC)
    db.add(
        ProcessingJob(
            id=job_id,
            event_id=f"ev-{job_id}",
            event_type=event_type,
            subscriber_id=subscriber_id,
            source="api:test",
            payload={"activity_id": 1},
            status=status,
            attempts=attempts,
            max_attempts=5,
            available_at=now,
            created_at=now,
            updated_at=updated_at or now,
            last_error="boom" if status == "dead_letter" else None,
            completed_at=now if status in ("completed", "dead_letter") else None,
        )
    )
    db.commit()


class TestGetJobsSummary:
    def test_aggregates_counts_and_by_subscriber(self, db):
        _insert_job(db, job_id="j1", subscriber_id="sub.a", status="completed")
        _insert_job(db, job_id="j2", subscriber_id="sub.a", status="completed")
        _insert_job(db, job_id="j3", subscriber_id="sub.a", status="pending")
        _insert_job(db, job_id="j4", subscriber_id="sub.b", status="dead_letter")

        summary = jobs_crud.get_jobs_summary(db)

        assert summary.total_jobs == 4
        assert summary.completed == 2
        assert summary.pending == 1
        assert summary.dead_letter == 1
        by_sub = {stats.subscriber_id: stats for stats in summary.by_subscriber}
        assert by_sub["sub.a"].total == 3
        assert by_sub["sub.a"].completed == 2
        assert by_sub["sub.a"].pending == 1
        assert by_sub["sub.b"].dead_letter == 1
        assert summary.oldest_pending_seconds is not None

    def test_recent_dead_letter_lists_jobs(self, db):
        _insert_job(db, job_id="dl1", subscriber_id="sub.b", status="dead_letter")
        summary = jobs_crud.get_jobs_summary(db)
        assert [job.id for job in summary.recent_dead_letter] == ["dl1"]
        assert summary.recent_dead_letter[0].last_error == "boom"

    def test_empty_summary(self, db):
        summary = jobs_crud.get_jobs_summary(db)
        assert summary.total_jobs == 0
        assert summary.by_subscriber == []
        assert summary.recent_dead_letter == []
        assert summary.oldest_pending_seconds is None


class TestReplayDeadLetterJob:
    def test_requeues_dead_letter_job(self, db):
        _insert_job(db, job_id="dl1", subscriber_id="sub.b", status="dead_letter", attempts=5)
        now = datetime.now(UTC) + timedelta(minutes=1)
        assert jobs_crud.replay_dead_letter_job("dl1", now=now, db=db) is True
        job = jobs_crud.get_job("dl1", db)
        assert job is not None
        assert job.status == "pending"
        assert job.attempts == 0
        assert job.last_error is None
        assert job.completed_at is None

    def test_ignores_non_dead_letter_job(self, db):
        _insert_job(db, job_id="c1", subscriber_id="sub.a", status="completed")
        assert jobs_crud.replay_dead_letter_job("c1", now=datetime.now(UTC), db=db) is False
        assert jobs_crud.get_job("c1", db).status == "completed"

    def test_missing_job_returns_false(self, db):
        assert jobs_crud.replay_dead_letter_job("nope", now=datetime.now(UTC), db=db) is False
