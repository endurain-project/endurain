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


class TestHandlerNameIsBounded:
    """``handler_name`` grows with the subscriber count and must never overflow.

    It stores the comma-joined names of every subscriber that ran. At
    ``varchar(100)`` that overflowed once ``activity.created`` reached four
    subscribers (125 chars) and ``activity.deleted`` three (101 — one over), and
    PostgreSQL rejected the whole UPDATE. Because event-log writes are
    best-effort (the recorder swallows storage errors so observability cannot
    break processing), nothing surfaced: the handlers had already run, so the
    work completed while the row stayed at ``published`` forever.
    """

    def test_completed_write_survives_an_oversized_handler_list(self, db):
        event_log_crud.record_published(_event(), db)
        # Far more subscribers than any event has today.
        handlers = ",".join(f"on_activity_created_subscriber_number_{i}" for i in range(40))

        event_log_crud.mark_completed("e1", handlers, 5, db)

        row = db.get(EventLog, "e1")
        # The lifecycle transition is what matters: it must not be lost.
        assert row.status == "completed"
        assert row.completed_at is not None
        assert len(row.handler_name) <= 500
        # Marked, so a reader can tell the list was cut rather than assume it is
        # the complete set of subscribers.
        assert row.handler_name.endswith("...")

    def test_failed_write_survives_an_oversized_handler_list(self, db):
        event_log_crud.record_published(_event(), db)
        handlers = ",".join(f"on_activity_created_subscriber_number_{i}" for i in range(40))

        event_log_crud.mark_failed("e1", handlers, "boom", 5, db)

        row = db.get(EventLog, "e1")
        assert row.status == "failed"
        assert len(row.handler_name) <= 500

    def test_a_list_that_fits_is_stored_verbatim(self, db):
        event_log_crud.record_published(_event(), db)
        handlers = "cleanup_activity_thumbnail_for_event,cleanup_activity_file_for_event"

        event_log_crud.mark_completed("e1", handlers, 5, db)

        assert db.get(EventLog, "e1").handler_name == handlers

    def test_the_real_subscriber_lists_fit(self):
        """The concrete lists that broke production must fit with headroom."""
        from collections import defaultdict

        import modules.activities.subscriber_registry as activity_registry

        class _Bus:
            def __init__(self):
                self.handlers = defaultdict(list)

            def subscribe(self, event_type, handler):
                self.handlers[event_type].append(handler)

        bus = _Bus()
        activity_registry.register_all_activity_bus_subscribers(bus)

        for event_type, handlers in bus.handlers.items():
            joined = ",".join(h.__name__ for h in handlers)
            assert len(joined) <= 500, f"{event_type} handler list is {len(joined)} chars"


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


class TestDeleteEventsBefore:
    @staticmethod
    def _add(db, event_id, created_at, status="completed"):
        db.add(
            EventLog(
                id=event_id,
                event_type="activity.created",
                event_source="api:test",
                event_payload={"activity_id": 1},
                status=status,
                created_at=created_at,
            )
        )
        db.commit()

    def test_deletes_only_rows_older_than_cutoff(self, db):
        cutoff = datetime(2026, 6, 1, tzinfo=UTC)
        self._add(db, "old", datetime(2026, 1, 1, tzinfo=UTC))
        self._add(db, "recent", datetime(2026, 7, 1, tzinfo=UTC))

        assert event_log_crud.delete_events_before(cutoff, db=db) == 1
        assert db.get(EventLog, "old") is None
        assert db.get(EventLog, "recent") is not None

    def test_prunes_every_status(self, db):
        cutoff = datetime(2026, 6, 1, tzinfo=UTC)
        old = datetime(2026, 1, 1, tzinfo=UTC)
        for i, status in enumerate(("completed", "failed", "queued", "processing")):
            self._add(db, f"e{i}", old, status=status)

        # event_log is best-effort/safe-to-lose, so every status is prunable.
        assert event_log_crud.delete_events_before(cutoff, db=db) == 4

    def test_batches_until_exhausted(self, db):
        cutoff = datetime(2026, 6, 1, tzinfo=UTC)
        old = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(5):
            self._add(db, f"e{i}", old)

        assert event_log_crud.delete_events_before(cutoff, db=db, batch_size=2) == 5
        for i in range(5):
            assert db.get(EventLog, f"e{i}") is None

    def test_returns_zero_when_nothing_old(self, db):
        self._add(db, "recent", datetime(2026, 7, 1, tzinfo=UTC))
        assert event_log_crud.delete_events_before(datetime(2026, 6, 1, tzinfo=UTC), db=db) == 0
