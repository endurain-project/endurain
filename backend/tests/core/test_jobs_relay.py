"""Tests for the outbox relay — fan-out to per-subscriber jobs, mark relayed."""

from datetime import UTC, datetime

import pytest

import infra.events as platform_events
import infra.jobs.outbox as jobs_outbox
import infra.jobs.relay as jobs_relay
from infra.jobs.models import EventOutbox, ProcessingJob
from infra.jobs.registry import JobHandlerRegistry
from tests._helpers.db import create_sqlite_session_factory

_NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=UTC)


class _FakeClock:
    def now(self) -> datetime:
        return _NOW

    def monotonic(self) -> float:
        return 0.0


@pytest.fixture
def factory():
    session_factory = create_sqlite_session_factory()
    yield session_factory
    session_factory.kw["bind"].dispose()  # StaticPool keeps one connection; dispose to avoid ResourceWarning


def _noop(event: platform_events.Event) -> None:  # pragma: no cover - never invoked by the relay
    return None


def _event(event_id="e1", event_type="activity.created"):
    return platform_events.Event(
        event_id=event_id,
        event_type=event_type,
        source="api:store_activity",
        timestamp="2026-07-14T12:00:00+00:00",
        payload={"activity_id": 42, "user_id": 3},
        metadata={"activity_id": 42},
        retry_count=0,
    )


def _registry(*subscriber_ids):
    reg = JobHandlerRegistry()
    for subscriber_id in subscriber_ids:
        reg.register("activity.created", subscriber_id, _noop)
    return reg


def _relay(factory, registry, *, batch_size=10):
    return jobs_relay.relay_outbox_once(
        registry=registry,
        clock=_FakeClock(),
        session_factory=factory,
        max_attempts=5,
        batch_size=batch_size,
    )


class TestRelayOutboxOnce:
    def test_fans_out_one_job_per_subscriber(self, factory):
        with factory() as db:
            jobs_outbox.add_to_outbox(_event(), now=_NOW, db=db)
        relayed = _relay(factory, _registry("thumb.generate", "zones.compute"))
        assert relayed == 1
        with factory() as db:
            jobs = db.query(ProcessingJob).order_by(ProcessingJob.subscriber_id).all()
            assert [job.subscriber_id for job in jobs] == ["thumb.generate", "zones.compute"]
            assert all(job.event_id == "e1" and job.status == "pending" for job in jobs)
            assert db.query(EventOutbox).one().relayed_at is not None

    def test_marks_relayed_even_without_subscribers(self, factory):
        with factory() as db:
            jobs_outbox.add_to_outbox(_event(), now=_NOW, db=db)
        relayed = _relay(factory, JobHandlerRegistry())
        assert relayed == 1
        with factory() as db:
            assert db.query(ProcessingJob).count() == 0
            assert db.query(EventOutbox).one().relayed_at is not None

    def test_is_idempotent_on_rerun(self, factory):
        with factory() as db:
            jobs_outbox.add_to_outbox(_event(), now=_NOW, db=db)
        registry = _registry("thumb.generate")
        _relay(factory, registry)
        # A second pass sees no unrelayed rows and enqueues nothing new.
        assert _relay(factory, registry) == 0
        with factory() as db:
            assert db.query(ProcessingJob).count() == 1

    def test_respects_batch_size(self, factory):
        with factory() as db:
            for index in range(3):
                jobs_outbox.add_to_outbox(_event(f"e{index}"), now=_NOW, db=db)
        assert _relay(factory, _registry("thumb.generate"), batch_size=2) == 2
        with factory() as db:
            assert db.query(ProcessingJob).count() == 2
            assert len(jobs_outbox.list_unrelayed(limit=10, db=db)) == 1
