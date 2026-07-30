"""Tests for the durable-job runner — claim, run, complete/fail, reap."""

from datetime import UTC, datetime, timedelta

import pytest

import infra.events as platform_events
import infra.jobs.crud as jobs_crud
from infra.jobs.models import ProcessingJob
from infra.jobs.registry import JobHandlerRegistry
from infra.jobs.runner import JobRunner
from tests._helpers.db import create_sqlite_session_factory

_NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)


class _FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return 0.0


@pytest.fixture
def factory():
    session_factory = create_sqlite_session_factory()
    yield session_factory
    session_factory.kw["bind"].dispose()  # StaticPool keeps one connection; dispose to avoid ResourceWarning


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


def _runner(factory, registry, clock=None):
    return JobRunner(
        registry=registry,
        clock=clock or _FakeClock(_NOW),
        session_factory=factory,
        worker_id="w1",
        lease_seconds=300,
        batch_size=10,
        backoff_base_seconds=5.0,
        backoff_max_seconds=3600.0,
    )


def _enqueue(factory, subscriber_id="sub.a", *, max_attempts=3, event=None):
    with factory() as db:
        jobs_crud.enqueue_job(event or _event(), subscriber_id, max_attempts=max_attempts, now=_NOW, db=db)


def _only_job(factory) -> ProcessingJob:
    with factory() as db:
        return db.query(ProcessingJob).one()


def _raise(event: platform_events.Event) -> None:
    raise ValueError("boom")


class TestRunOnce:
    def test_completes_successful_job(self, factory):
        seen: list[platform_events.Event] = []
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", seen.append)
        _enqueue(factory)
        processed = _runner(factory, reg).run_once()
        assert processed == 1
        assert [event.payload["activity_id"] for event in seen] == [42]
        assert seen[0].event_type == "activity.created"
        assert seen[0].metadata == {"activity_id": 42}
        job = _only_job(factory)
        assert job.status == "completed"
        assert job.attempts == 1

    def test_reschedules_failed_job_with_attempts_remaining(self, factory):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", _raise)
        _enqueue(factory, max_attempts=3)
        _runner(factory, reg).run_once()
        job = _only_job(factory)
        assert job.status == "pending"
        assert job.attempts == 1
        assert job.last_error == "boom"

    def test_dead_letters_failed_job_when_exhausted(self, factory):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", _raise)
        _enqueue(factory, max_attempts=1)
        _runner(factory, reg).run_once()
        assert _only_job(factory).status == "dead_letter"

    def test_missing_handler_fails_job(self, factory):
        _enqueue(factory, "sub.missing", max_attempts=1)
        _runner(factory, JobHandlerRegistry()).run_once()
        job = _only_job(factory)
        assert job.status == "dead_letter"
        assert job.last_error is not None
        assert "no durable handler" in job.last_error

    def test_returns_zero_when_nothing_due(self, factory):
        assert _runner(factory, JobHandlerRegistry()).run_once() == 0

    def test_finalize_error_does_not_abort_batch(self, factory, monkeypatch):
        reg = JobHandlerRegistry()
        reg.register("activity.created", "sub.a", lambda event: None)
        _enqueue(factory)

        def _boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr(jobs_crud, "mark_job_completed", _boom)
        # The completion write fails but run_once still reports the job as processed.
        assert _runner(factory, reg).run_once() == 1


class TestReapOnce:
    def test_reclaims_expired_lease(self, factory):
        _enqueue(factory)
        with factory() as db:
            jobs_crud.claim_jobs(worker_id="dead", limit=10, lease_seconds=300, now=_NOW, db=db)
        runner = _runner(factory, JobHandlerRegistry(), clock=_FakeClock(_NOW + timedelta(seconds=400)))
        assert runner.reap_once() == 1
        assert _only_job(factory).status == "pending"

    def test_nothing_to_reap(self, factory):
        assert _runner(factory, JobHandlerRegistry()).reap_once() == 0
