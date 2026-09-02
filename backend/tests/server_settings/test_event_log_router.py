"""Tests for the event_log admin route handler."""

from unittest.mock import MagicMock, patch

import modules.server_settings.event_log_router as event_log_router


class TestReadEventLogSummary:
    def test_delegates_with_hours(self):
        sentinel = MagicMock()
        with patch(
            "modules.server_settings.event_log_router.jasil_admin.get_event_log_summary",
            return_value=sentinel,
        ) as get_summary:
            result = event_log_router.read_event_log_summary(_check_scopes=None, hours=12)
        assert result is sentinel
        get_summary.assert_called_once_with(hours=12)

    def test_defaults_to_24_hours(self):
        with patch("modules.server_settings.event_log_router.jasil_admin.get_event_log_summary") as get_summary:
            event_log_router.read_event_log_summary(_check_scopes=None)
        get_summary.assert_called_once_with(hours=24)
