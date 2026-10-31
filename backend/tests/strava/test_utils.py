"""Tests for strava.utils helper functions."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import pytest
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


class TestRateLimitTrackerIsSharedState:
    """The limits are Strava's, per application, so every process must see the same answer."""

    @pytest.fixture
    def tracker(self):
        return strava_utils.StravaRateLimitTracker()

    def test_nothing_is_limited_to_begin_with(self, tracker):
        assert tracker.is_rate_limited() is False

    def test_a_short_term_limit_is_visible_to_another_tracker(self, tracker):
        """Two instances stand in for two processes: the flag lives in the platform state."""
        tracker.mark_rate_limited(is_long_term=False)

        assert strava_utils.StravaRateLimitTracker().is_rate_limited() is True

    def test_a_long_term_limit_is_visible_to_another_tracker(self, tracker):
        tracker.mark_rate_limited(is_long_term=True)

        assert strava_utils.StravaRateLimitTracker().is_rate_limited() is True

    def test_the_flag_expires_on_its_own(self, tracker):
        import jasil.runtime as platform_runtime

        tracker.mark_rate_limited(is_long_term=False)
        platform_runtime.get_active_platform().state.delete(tracker._SHORT_TERM_KEY)

        assert tracker.is_rate_limited() is False

    def test_an_unreachable_state_store_fails_open(self, tracker, monkeypatch):
        """A missed back-off costs one rejected call, which marks the limit again."""
        from jasil.providers import StateBackendUnavailableError

        def _down():
            raise StateBackendUnavailableError("redis down")

        monkeypatch.setattr(tracker, "_state", _down)

        assert tracker.is_rate_limited() is False
        tracker.mark_rate_limited()  # must not raise


class TestRefreshUserStravaToken:
    def _integrations(self, expires_in_minutes: int):
        from datetime import UTC, datetime, timedelta

        return Mock(
            user_id=1,
            strava_token="t",
            strava_refresh_token="r",
            strava_client_id="c",
            strava_client_secret="s",
            strava_token_expires_at=datetime.now(UTC) + timedelta(minutes=expires_in_minutes),
        )

    @pytest.fixture(autouse=True)
    def _session(self, monkeypatch):
        monkeypatch.setattr(strava_utils, "SessionLocal", lambda: MagicMock())

    def test_a_token_far_from_expiry_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(
            strava_utils.user_integrations_crud,
            "get_user_integrations_by_user_id",
            Mock(return_value=self._integrations(expires_in_minutes=600)),
        )
        create_client = Mock()
        monkeypatch.setattr(strava_utils, "create_strava_client", create_client)

        strava_utils.refresh_user_strava_token(1)

        create_client.assert_not_called()

    def test_an_expiring_token_is_refreshed_and_stored_with_no_session_open_for_the_call(self, monkeypatch):
        monkeypatch.setattr(
            strava_utils.user_integrations_crud,
            "get_user_integrations_by_user_id",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        open_sessions = 0
        during_call: list[int] = []

        class _Session:
            def __enter__(self):
                nonlocal open_sessions
                open_sessions += 1
                return MagicMock()

            def __exit__(self, *_exc):
                nonlocal open_sessions
                open_sessions -= 1
                return False

        monkeypatch.setattr(strava_utils, "SessionLocal", _Session)
        client = Mock()
        client.refresh_access_token.side_effect = lambda **_k: (
            during_call.append(open_sessions) or {"access_token": "n"}
        )
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))
        link = Mock()
        monkeypatch.setattr(strava_utils.user_integrations_crud, "link_strava_account", link)

        strava_utils.refresh_user_strava_token(1)

        assert during_call == [0]
        link.assert_called_once()

    def test_a_rate_limited_refresh_marks_the_limit_and_returns(self, monkeypatch):
        monkeypatch.setattr(
            strava_utils.user_integrations_crud,
            "get_user_integrations_by_user_id",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        client = Mock()
        client.refresh_access_token.side_effect = RuntimeError("429 rate limit exceeded")
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))
        link = Mock()
        monkeypatch.setattr(strava_utils.user_integrations_crud, "link_strava_account", link)

        strava_utils.refresh_user_strava_token(1)

        assert strava_utils.rate_limit_tracker.is_rate_limited() is True
        link.assert_not_called()

    def test_an_unexpected_failure_is_logged_not_raised(self, monkeypatch):
        """The sync that follows fails visibly if the token really is unusable."""
        monkeypatch.setattr(
            strava_utils.user_integrations_crud,
            "get_user_integrations_by_user_id",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        client = Mock()
        client.refresh_access_token.side_effect = ValueError("bad refresh token")
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))

        strava_utils.refresh_user_strava_token(1)  # must not raise
