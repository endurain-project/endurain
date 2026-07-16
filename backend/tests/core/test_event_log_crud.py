"""Tests for event_log CRUD — recording writes and dashboard aggregates."""

from datetime import UTC, datetime

import pytest

import infra.event_log.crud as event_log_crud
import infra.events as platform_events
from infra.event_log.models import EventLog
from tests._helpers.db import create_sqlite_session


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
        timestamp="2026-07-09T00:00:00+00:00",
        payload={"activity_id": 42},
        metadata=metadata if metadata is not None else {"activity_id": 42},
        retry_count=0,
    )


class TestRecordingWrites:
    def test_record_published_inserts_row(self, db):
        event_log_crud.record_published(_event(), db)
        row = db.get(EventLog, "e1")
        assert row.status == "published"
        assert row.event_type == "activity.created"
        assert row.event_source == "api:test"
        assert row.event_payload == {"activity_id": 42}
        assert row.event_metadata == {"activity_id": 42}

    def test_record_published_stores_empty_metadata_as_null(self, db):
        event_log_crud.record_published(_event(metadata={}), db)
        assert db.get(EventLog, "e1").event_metadata is None

    def test_mark_processing_sets_worker_and_timestamp(self, db):
        event_log_crud.record_published(_event(), db)
        event_log_crud.mark_processing("e1", "worker-1", db)
        row = db.get(EventLog, "e1")
        assert row.status == "processing"
        assert row.worker_id == "worker-1"
        assert row.processed_at is not None

    def test_mark_completed_sets_timing_and_handler(self, db):
        event_log_crud.record_published(_event(), db)
        event_log_crud.mark_completed("e1", "on_activity_created", 123, db)
        row = db.get(EventLog, "e1")
        assert row.status == "completed"
        assert row.handler_name == "on_activity_created"
        assert row.processing_time_ms == 123
        assert row.completed_at is not None

    def test_mark_failed_truncates_long_error(self, db):
        event_log_crud.record_published(_event(), db)
        event_log_crud.mark_failed("e1", "handler", "x" * 5000, 7, db)
        row = db.get(EventLog, "e1")
        assert row.status == "failed"
        assert row.error_message is not None
        assert len(row.error_message) == 4000
        assert row.processing_time_ms == 7

    def test_record_queued_inserts_terminal_row(self, db):
        event_log_crud.record_queued(_event(), db)
        row = db.get(EventLog, "e1")
        assert row.status == "queued"
        assert row.event_type == "activity.created"


class TestSummary:
    def test_counts_by_type_and_latency(self, db):
        event_log_crud.record_published(_event("e1", "activity.created"), db)
        event_log_crud.mark_completed("e1", "h", 100, db)
        event_log_crud.record_published(_event("e2", "activity.created"), db)
        event_log_crud.mark_failed("e2", "h", "boom", 50, db)
        event_log_crud.record_published(_event("e3", "user.created"), db)

        summary = event_log_crud.get_event_log_summary(db, hours=24)

        assert summary.window_hours == 24
        assert summary.total_events == 3
        by_type = {stats.event_type: stats for stats in summary.by_type}
        assert by_type["activity.created"].total == 2
        assert by_type["activity.created"].completed == 1
        assert by_type["activity.created"].failed == 1
        assert by_type["activity.created"].avg_processing_time_ms == 75.0
        assert by_type["activity.created"].max_processing_time_ms == 100
        assert by_type["user.created"].published == 1
        assert by_type["user.created"].avg_processing_time_ms is None

    def test_queued_events_count_in_totals_not_pending(self, db):
        event_log_crud.record_queued(_event("q1", "activity.created"), db)

        summary = event_log_crud.get_event_log_summary(db, hours=24)

        by_type = {stats.event_type: stats for stats in summary.by_type}
        assert by_type["activity.created"].queued == 1
        assert by_type["activity.created"].total == 1
        # 'queued' is terminal in event_log: durable events must not show as pending.
        assert summary.pending == []

    def test_pending_and_recent_failures(self, db):
        event_log_crud.record_published(_event("e1"), db)  # stays published => pending
        event_log_crud.record_published(_event("e2"), db)
        event_log_crud.mark_failed("e2", "h", "boom", 5, db)

        summary = event_log_crud.get_event_log_summary(db)

        pending = {(group.event_type, group.status): group for group in summary.pending}
        assert ("activity.created", "published") in pending
        assert pending[("activity.created", "published")].count == 1
        assert pending[("activity.created", "published")].oldest_seconds is not None
        assert [failure.id for failure in summary.recent_failures] == ["e2"]
        assert summary.recent_failures[0].error_message == "boom"
        assert summary.recent_failures[0].event_metadata == {"activity_id": 42}

    def test_recent_failures_respects_limit(self, db):
        for index in range(5):
            event_log_crud.record_published(_event(f"e{index}"), db)
            event_log_crud.mark_failed(f"e{index}", "h", "boom", 1, db)
        summary = event_log_crud.get_event_log_summary(db, failure_limit=3)
        assert len(summary.recent_failures) == 3

    def test_empty_table_returns_zeroed_summary(self, db):
        summary = event_log_crud.get_event_log_summary(db)
        assert summary.total_events == 0
        assert summary.by_type == []
        assert summary.pending == []
        assert summary.recent_failures == []


class TestAgeSeconds:
    def test_none_moment_returns_none(self):
        assert event_log_crud._age_seconds(None, datetime.now(UTC)) is None

    def test_timezone_aware_moment_is_computed_directly(self):
        now = datetime(2026, 7, 9, 12, 0, 0, tzinfo=UTC)
        moment = datetime(2026, 7, 9, 11, 0, 0, tzinfo=UTC)
        assert event_log_crud._age_seconds(moment, now) == 3600.0
