"""Tests for the EventLogRecorder lifecycle and error-swallowing behavior."""

from unittest.mock import patch

import pytest

import core.platform.events as platform_events
from core.event_log.recorder import EventLogRecorder


def _event():
    return platform_events.Event(
        event_id="e1",
        event_type="activity.created",
        source="api:test",
        timestamp="2026-07-09T00:00:00+00:00",
        payload={"activity_id": 42},
        metadata={"activity_id": 42},
        retry_count=0,
    )


class TestRecordPublished:
    def test_opens_session_and_calls_crud(self):
        with (
            patch("core.event_log.recorder.SessionLocal"),
            patch("core.event_log.recorder.event_log_crud.record_published") as record,
        ):
            EventLogRecorder().record_published(_event())
        record.assert_called_once()

    def test_storage_error_is_swallowed_and_logged(self):
        with (
            patch("core.event_log.recorder.SessionLocal", side_effect=RuntimeError("db down")),
            patch("core.event_log.recorder.core_logger.print_to_log") as log,
        ):
            EventLogRecorder().record_published(_event())  # must not raise
        log.assert_called_once()


class TestTrack:
    def test_records_processing_then_completed_around_body(self):
        order: list[str] = []
        with (
            patch("core.event_log.recorder.SessionLocal"),
            patch(
                "core.event_log.recorder.event_log_crud.mark_processing",
                side_effect=lambda *a: order.append("processing"),
            ),
            patch(
                "core.event_log.recorder.event_log_crud.mark_completed",
                side_effect=lambda *a: order.append("completed"),
            ),
        ):
            recorder = EventLogRecorder()
            with recorder.track(_event(), worker_id="w", handler_name="h"):
                order.append("body")
        assert order == ["processing", "body", "completed"]

    def test_records_failed_and_reraises(self):
        with (
            patch("core.event_log.recorder.SessionLocal"),
            patch("core.event_log.recorder.event_log_crud.mark_processing"),
            patch("core.event_log.recorder.event_log_crud.mark_completed") as completed,
            patch("core.event_log.recorder.event_log_crud.mark_failed") as failed,
        ):
            recorder = EventLogRecorder()
            with pytest.raises(ValueError, match="boom"), recorder.track(_event(), worker_id="w", handler_name="h"):
                raise ValueError("boom")
        failed.assert_called_once()
        completed.assert_not_called()

    def test_completion_storage_error_does_not_break_processing(self):
        with (
            patch("core.event_log.recorder.SessionLocal", side_effect=RuntimeError("db down")),
            patch("core.event_log.recorder.core_logger.print_to_log"),
        ):
            recorder = EventLogRecorder()
            with recorder.track(_event(), worker_id="w", handler_name="h"):
                pass  # body succeeds; the failing storage writes must be swallowed
