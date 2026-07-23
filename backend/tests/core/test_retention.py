"""Tests for the substrate retention-pruning orchestration."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import infra.retention as platform_retention

_NOW = datetime(2026, 7, 23, tzinfo=UTC)


@contextmanager
def _lock(acquired: bool):
    yield acquired


def _platform(*, acquired: bool = True) -> MagicMock:
    platform = MagicMock()
    platform.lock.try_acquire.return_value = _lock(acquired)
    platform.clock.now.return_value = _NOW
    return platform


def _windows(*, event_log_days: int, jobs_days: int):
    return (
        patch.object(platform_retention.core_config.settings, "EVENT_LOG_RETENTION_DAYS", event_log_days),
        patch.object(platform_retention.core_config.settings, "JOBS_RETENTION_DAYS", jobs_days),
    )


class TestPruneExpiredRecords:
    @patch("infra.retention.platform_runtime")
    def test_noop_when_both_windows_disabled(self, mock_runtime):
        event_log_window, jobs_window = _windows(event_log_days=0, jobs_days=0)
        with event_log_window, jobs_window:
            platform_retention.prune_expired_records()

        # Both windows disabled (<= 0): never even resolves the platform.
        mock_runtime.get_active_platform.assert_not_called()

    @patch("infra.retention.jobs_crud")
    @patch("infra.retention.jobs_outbox")
    @patch("infra.retention.event_log_crud")
    @patch("infra.retention.core_database")
    @patch("infra.retention.platform_runtime")
    def test_skips_when_lock_not_acquired(self, mock_runtime, mock_db, mock_el, mock_ob, mock_jc):
        mock_runtime.get_active_platform.return_value = _platform(acquired=False)

        event_log_window, jobs_window = _windows(event_log_days=90, jobs_days=90)
        with event_log_window, jobs_window:
            platform_retention.prune_expired_records()

        mock_el.delete_events_before.assert_not_called()
        mock_ob.delete_relayed_before.assert_not_called()
        mock_jc.delete_completed_jobs_before.assert_not_called()

    @patch("infra.retention.jobs_crud")
    @patch("infra.retention.jobs_outbox")
    @patch("infra.retention.event_log_crud")
    @patch("infra.retention.core_database")
    @patch("infra.retention.platform_runtime")
    def test_prunes_each_table_with_its_own_window(self, mock_runtime, mock_db, mock_el, mock_ob, mock_jc):
        mock_runtime.get_active_platform.return_value = _platform()
        mock_el.delete_events_before.return_value = 3
        mock_ob.delete_relayed_before.return_value = 2
        mock_jc.delete_completed_jobs_before.return_value = 1

        # Independent windows: event_log trimmed at 30d, durable-job tables at 90d.
        event_log_window, jobs_window = _windows(event_log_days=30, jobs_days=90)
        with event_log_window, jobs_window:
            platform_retention.prune_expired_records()

        assert mock_el.delete_events_before.call_args.args[0] == _NOW - timedelta(days=30)
        assert mock_ob.delete_relayed_before.call_args.args[0] == _NOW - timedelta(days=90)
        assert mock_jc.delete_completed_jobs_before.call_args.args[0] == _NOW - timedelta(days=90)

    @patch("infra.retention.jobs_crud")
    @patch("infra.retention.jobs_outbox")
    @patch("infra.retention.event_log_crud")
    @patch("infra.retention.core_database")
    @patch("infra.retention.platform_runtime")
    def test_event_log_window_disabled_prunes_only_jobs(self, mock_runtime, mock_db, mock_el, mock_ob, mock_jc):
        mock_runtime.get_active_platform.return_value = _platform()

        event_log_window, jobs_window = _windows(event_log_days=0, jobs_days=90)
        with event_log_window, jobs_window:
            platform_retention.prune_expired_records()

        mock_el.delete_events_before.assert_not_called()
        mock_ob.delete_relayed_before.assert_called_once()
        mock_jc.delete_completed_jobs_before.assert_called_once()

    @patch("infra.retention.jobs_crud")
    @patch("infra.retention.jobs_outbox")
    @patch("infra.retention.event_log_crud")
    @patch("infra.retention.core_database")
    @patch("infra.retention.platform_runtime")
    def test_jobs_window_disabled_prunes_only_event_log(self, mock_runtime, mock_db, mock_el, mock_ob, mock_jc):
        mock_runtime.get_active_platform.return_value = _platform()

        event_log_window, jobs_window = _windows(event_log_days=90, jobs_days=0)
        with event_log_window, jobs_window:
            platform_retention.prune_expired_records()

        mock_el.delete_events_before.assert_called_once()
        mock_ob.delete_relayed_before.assert_not_called()
        mock_jc.delete_completed_jobs_before.assert_not_called()
