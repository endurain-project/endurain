"""Tests for strava.utils helper functions."""

from __future__ import annotations

from unittest.mock import Mock

from stravalib.exc import Fault as StravaFault

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
# is_strava_not_found_error
# ---------------------------------------------------------------------------


class TestIsStravaNotFoundError:
    """Unit tests for strava_utils.is_strava_not_found_error."""

    def test_strava_fault_404_returns_true(self):
        """StravaFault with status_code 404 is detected as a not-found error."""
        err = _make_strava_fault(404)
        assert strava_utils.is_strava_not_found_error(err) is True

    def test_strava_fault_non_404_returns_false(self):
        """StravaFault with a non-404 status_code is not a not-found error."""
        err = _make_strava_fault(500)
        assert strava_utils.is_strava_not_found_error(err) is False

    def test_strava_fault_no_response_falls_back_to_str(self):
        """StravaFault with no response attribute falls back to string check."""
        fault = StravaFault()
        # No .response set — string representation is empty → False
        assert strava_utils.is_strava_not_found_error(fault) is False

    def test_plain_exception_with_not_found_text_returns_true(self):
        """Generic exception whose message contains 'not found' is detected."""
        err = ValueError("Resource Not Found")
        assert strava_utils.is_strava_not_found_error(err) is True

    def test_plain_exception_with_404_in_text_returns_true(self):
        """Generic exception whose message contains '404' is detected."""
        err = RuntimeError("HTTP 404 response received")
        assert strava_utils.is_strava_not_found_error(err) is True

    def test_plain_exception_unrelated_returns_false(self):
        """Generic exception with an unrelated message is not detected."""
        err = ValueError("Something completely different went wrong")
        assert strava_utils.is_strava_not_found_error(err) is False


# ---------------------------------------------------------------------------
# is_strava_rate_limit_error
# ---------------------------------------------------------------------------


class TestIsStravaRateLimitError:
    """Unit tests for strava_utils.is_strava_rate_limit_error."""

    def test_strava_fault_429_returns_true(self):
        """StravaFault with status_code 429 is detected as a rate-limit error."""
        err = _make_strava_fault(429)
        assert strava_utils.is_strava_rate_limit_error(err) is True

    def test_strava_fault_non_429_returns_false(self):
        """StravaFault with a non-429 status_code is not a rate-limit error."""
        err = _make_strava_fault(404)
        assert strava_utils.is_strava_rate_limit_error(err) is False

    def test_plain_exception_with_rate_limit_text_returns_true(self):
        """Generic exception whose message contains 'rate limit' is detected."""
        err = ValueError("Strava rate limit exceeded")
        assert strava_utils.is_strava_rate_limit_error(err) is True

    def test_plain_exception_with_429_in_text_returns_true(self):
        """Generic exception whose message contains '429' is detected."""
        err = RuntimeError("HTTP 429 Too Many Requests")
        assert strava_utils.is_strava_rate_limit_error(err) is True

    def test_plain_exception_unrelated_returns_false(self):
        """Generic exception with an unrelated message is not detected."""
        err = ValueError("Network timeout")
        assert strava_utils.is_strava_rate_limit_error(err) is False
