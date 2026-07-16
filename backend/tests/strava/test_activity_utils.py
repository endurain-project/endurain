"""Tests for strava.activity_utils stream-fetching logic."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from stravalib.exc import Fault as StravaFault

import modules.strava.activity_utils as activity_utils
import modules.strava.utils as strava_utils

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strava_fault(status_code: int) -> StravaFault:
    """Return a StravaFault whose .response.status_code equals *status_code*."""
    response = Mock()
    response.status_code = status_code
    fault = StravaFault()
    fault.response = response
    return fault


# ---------------------------------------------------------------------------
# fetch_and_process_activity_streams — empty-stream (404) path
# ---------------------------------------------------------------------------


class TestFetchAndProcessActivityStreamsNotFound:
    """Tests for the 404 / no-streams path in fetch_and_process_activity_streams."""

    def _call(self, client: Mock) -> tuple:
        return activity_utils.fetch_and_process_activity_streams(
            strava_client=client,
            strava_activity_id=99,
            user_id=1,
        )

    def test_not_found_fault_returns_empty_streams(self, monkeypatch):
        """A StravaFault 404 yields thirteen empty/False return values."""
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(404)

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(activity_utils.core_logger, "print_to_log", Mock())

        result = self._call(client)

        assert result == (
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
        )

    def test_not_found_plain_exception_returns_empty_streams(self, monkeypatch):
        """A generic 'not found' exception also yields empty stream data."""
        client = Mock()
        client.get_activity_streams.side_effect = RuntimeError("404 not found")

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(activity_utils.core_logger, "print_to_log", Mock())

        result = self._call(client)

        assert result == (
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
        )

    def test_rate_limit_fault_raises_429(self, monkeypatch):
        """A StravaFault 429 raises HTTPException 429, not empty streams."""
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(429)

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(strava_utils.rate_limit_tracker, "mark_rate_limited", Mock())
        monkeypatch.setattr(activity_utils.core_logger, "print_to_log", Mock())

        with pytest.raises(HTTPException) as exc_info:
            self._call(client)

        assert exc_info.value.status_code == 429

    def test_pre_check_rate_limited_raises_429(self, monkeypatch):
        """When already rate-limited, raises HTTPException 429 before any API call."""
        client = Mock()

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: True)
        monkeypatch.setattr(activity_utils.core_logger, "print_to_log", Mock())

        with pytest.raises(HTTPException) as exc_info:
            self._call(client)

        assert exc_info.value.status_code == 429
        client.get_activity_streams.assert_not_called()

    def test_unrelated_exception_raises_424(self, monkeypatch):
        """An unrelated exception raises HTTPException 424."""
        client = Mock()
        client.get_activity_streams.side_effect = RuntimeError("network failure")

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(activity_utils.core_logger, "print_to_log", Mock())

        with pytest.raises(HTTPException) as exc_info:
            self._call(client)

        assert exc_info.value.status_code == 424
