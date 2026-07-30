"""Tests for the event_log admin route handler."""

from unittest.mock import MagicMock, patch

import modules.server_settings.event_log_router as event_log_router


class TestReadEventLogSummary:
    def test_delegates_to_crud_with_hours(self):
        fake_db = MagicMock()
        sentinel = MagicMock()
        with patch(
            "modules.server_settings.event_log_router.event_log_crud.get_event_log_summary",
            return_value=sentinel,
        ) as get_summary:
            result = event_log_router.read_event_log_summary(_check_scopes=None, db=fake_db, hours=12)
        assert result is sentinel
        get_summary.assert_called_once_with(fake_db, hours=12)

    def test_defaults_to_24_hours(self):
        fake_db = MagicMock()
        with patch("modules.server_settings.event_log_router.event_log_crud.get_event_log_summary") as get_summary:
            event_log_router.read_event_log_summary(_check_scopes=None, db=fake_db)
        get_summary.assert_called_once_with(fake_db, hours=24)
