"""Tests for the Strava client service helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock

import jasil.runtime as platform_runtime
import pytest
from stravalib.exc import AccessUnauthorized, ObjectNotFound, RateLimitExceeded
from stravalib.exc import Fault as StravaFault

import core.exceptions as core_exceptions
import modules.strava.client_service as strava_utils
import modules.strava.rate_limit_store as strava_rate_limit_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strava_fault(status_code: int) -> StravaFault:
    """Return a StravaFault whose .response.status_code equals *status_code*."""
    response = Mock()
    response.status_code = status_code
    response.headers = {}
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

    def test_object_not_found_returns_true(self):
        assert strava_utils.is_strava_not_found_error(ObjectNotFound()) is True

    def test_message_text_alone_is_not_enough(self):
        """An id or message that merely contains the digits must not read as a 404."""
        assert strava_utils.is_strava_not_found_error(RuntimeError("activity 14042 failed: not found")) is False

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

    def test_rate_limit_exceeded_returns_true(self):
        assert strava_utils.is_strava_rate_limit_error(RateLimitExceeded("limit")) is True

    def test_message_text_alone_is_not_enough(self):
        """An activity id that merely contains 429 must not mark the application rate limited."""
        assert strava_utils.is_strava_rate_limit_error(RuntimeError("activity 14290429 failed")) is False

    def test_plain_exception_unrelated_returns_false(self):
        """Generic exception with an unrelated message is not detected."""
        err = ValueError("Network timeout")
        assert strava_utils.is_strava_rate_limit_error(err) is False


class TestGetClientId:
    def test_returns_the_decrypted_client_id(self, monkeypatch):
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: f"plain-{value}")

        assert strava_utils.get_client_id(Mock(strava_client_id="enc")) == "plain-enc"

    def test_a_missing_client_id_fails_loudly(self):
        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_utils.get_client_id(Mock(strava_client_id=None))


class TestRefreshUserStravaToken:
    @pytest.fixture
    def rate_limits(self):
        return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())

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
        monkeypatch.setattr(strava_utils.core_database, "SessionLocal", lambda: MagicMock())

    def test_a_token_far_from_expiry_is_left_alone(self, monkeypatch, rate_limits):
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(return_value=self._integrations(expires_in_minutes=600)),
        )
        create_client = Mock()
        monkeypatch.setattr(strava_utils, "create_strava_client", create_client)

        strava_utils.refresh_user_strava_token(1, rate_limits)

        create_client.assert_not_called()

    def test_an_expiring_token_is_refreshed_and_stored_with_no_session_open_for_the_call(
        self, monkeypatch, rate_limits, caplog
    ):
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
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

        monkeypatch.setattr(strava_utils.core_database, "SessionLocal", _Session)
        client = Mock()
        client.refresh_access_token.side_effect = lambda **_k: (
            during_call.append(open_sessions) or {"access_token": "n"}
        )
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))
        replace = Mock(return_value=True)
        monkeypatch.setattr(
            strava_utils.user_integrations_integration, "replace_strava_tokens_if_refresh_token", replace
        )

        with caplog.at_level("DEBUG", logger=strava_utils.logger.name):
            strava_utils.refresh_user_strava_token(1, rate_limits)

        assert during_call == [0]
        # A routine refresh, logged as Garmin Connect logs its own.
        refreshed = [record for record in caplog.records if record.getMessage() == "Strava tokens refreshed"]
        assert [record.levelname for record in refreshed] == ["DEBUG"]
        replace.assert_called_once()
        assert replace.call_args.args[:3] == (1, "r", {"access_token": "n"})

    def test_tokens_changed_since_the_read_are_not_overwritten(self, monkeypatch, rate_limits):
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        client = Mock()
        client.refresh_access_token.return_value = {"access_token": "n"}
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))
        db = MagicMock()
        monkeypatch.setattr(
            strava_utils.core_database,
            "SessionLocal",
            lambda: MagicMock(__enter__=lambda s: db, __exit__=lambda *a: False),
        )
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "replace_strava_tokens_if_refresh_token",
            Mock(return_value=False),
        )

        strava_utils.refresh_user_strava_token(1, rate_limits)

        db.commit.assert_not_called()

    def test_a_rate_limited_refresh_marks_the_limit_and_returns(self, monkeypatch, rate_limits):
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        client = Mock()
        client.refresh_access_token.side_effect = _make_strava_fault(429)
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))
        replace = Mock()
        monkeypatch.setattr(
            strava_utils.user_integrations_integration, "replace_strava_tokens_if_refresh_token", replace
        )

        strava_utils.refresh_user_strava_token(1, rate_limits)

        assert rate_limits.is_rate_limited("c") is True
        assert rate_limits.is_rate_limited("another-app") is False
        replace.assert_not_called()

    def test_another_apps_limit_does_not_skip_the_refresh(self, monkeypatch, rate_limits):
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        rate_limits.mark_rate_limited("another-app", is_long_term=True)
        client = Mock()
        client.refresh_access_token.return_value = {"access_token": "n"}
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))
        monkeypatch.setattr(strava_utils.user_integrations_integration, "link_strava_account", Mock())

        strava_utils.refresh_user_strava_token(1, rate_limits)

        client.refresh_access_token.assert_called_once()

    def test_a_limited_app_skips_the_refresh(self, monkeypatch, rate_limits):
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        rate_limits.mark_rate_limited("c", is_long_term=True)
        create_client = Mock()
        monkeypatch.setattr(strava_utils, "create_strava_client", create_client)

        strava_utils.refresh_user_strava_token(1, rate_limits)

        create_client.assert_not_called()

    def test_an_unexpected_failure_is_logged_not_raised(self, monkeypatch, rate_limits):
        """The sync that follows fails visibly if the token really is unusable."""
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        client = Mock()
        client.refresh_access_token.side_effect = ValueError("bad refresh token")
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))

        strava_utils.refresh_user_strava_token(1, rate_limits)  # must not raise

    def test_a_failed_store_of_the_rotated_tokens_is_logged_as_an_error_not_raised(
        self, monkeypatch, rate_limits, caplog
    ):
        """Strava invalidated the old refresh token, so the loss is named; the sync then fails visibly and unlinks."""
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(return_value=self._integrations(expires_in_minutes=10)),
        )
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
        client = Mock()
        client.refresh_access_token.return_value = {"access_token": "n"}
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))
        db = MagicMock()
        monkeypatch.setattr(
            strava_utils.core_database,
            "SessionLocal",
            lambda: MagicMock(__enter__=lambda s, db=db: db, __exit__=lambda *a: False),
        )
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "replace_strava_tokens_if_refresh_token",
            Mock(side_effect=RuntimeError("database down")),
        )

        with caplog.at_level("ERROR"):
            strava_utils.refresh_user_strava_token(1, rate_limits)  # must not raise

        assert any("could not be stored" in record.getMessage() for record in caplog.records)


class TestRaiseIfRateLimited:
    def test_a_rate_limit_is_recorded_and_refused(self):
        rate_limits = MagicMock()

        with pytest.raises(core_exceptions.TooManyRequestsError):
            strava_utils.raise_if_rate_limited(_make_strava_fault(429), "c", rate_limits)

        rate_limits.mark_rate_limited.assert_called_once_with("c", is_long_term=False)

    @pytest.mark.parametrize(
        ("headers", "long_term"),
        [
            ({"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "205,1500"}, False),
            ({"X-RateLimit-Limit": "200,2000", "X-RateLimit-Usage": "40,2001"}, True),
            ({"x-ratelimit-limit": "200,2000", "x-ratelimit-usage": "40,2000"}, True),
            ({"X-ReadRateLimit-Limit": "100,1000", "X-ReadRateLimit-Usage": "20,1000"}, True),
            ({"X-RateLimit-Limit": "garbage", "X-RateLimit-Usage": "1"}, False),
            ({}, False),
        ],
    )
    def test_the_daily_limit_is_read_from_the_response_headers(self, headers, long_term):
        rate_limits = MagicMock()
        fault = _make_strava_fault(429)
        fault.response.headers = headers
        fault.args = ("the text says daily but the headers decide",)

        with pytest.raises(core_exceptions.TooManyRequestsError):
            strava_utils.raise_if_rate_limited(fault, "c", rate_limits)

        rate_limits.mark_rate_limited.assert_called_once_with("c", is_long_term=long_term)

    def test_an_error_without_a_response_is_a_short_term_limit(self):
        rate_limits = MagicMock()

        with pytest.raises(core_exceptions.TooManyRequestsError):
            strava_utils.raise_if_rate_limited(RateLimitExceeded("limit"), "c", rate_limits)

        rate_limits.mark_rate_limited.assert_called_once_with("c", is_long_term=False)

    def test_any_other_error_passes_through(self):
        rate_limits = MagicMock()

        strava_utils.raise_if_rate_limited(ValueError("nope"), "c", rate_limits)

        rate_limits.mark_rate_limited.assert_not_called()


class TestRateLimitErrorsCarryTheRetryTime:
    def test_a_limit_just_hit_says_when_it_clears(self):
        from datetime import UTC, datetime

        clears = datetime(2026, 1, 1, 12, 15, tzinfo=UTC)
        rate_limits = MagicMock()
        rate_limits.mark_rate_limited.return_value = clears

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_utils.raise_if_rate_limited(_make_strava_fault(429), "c", rate_limits)

        assert raised.value.retry_at == clears

    def test_an_active_limit_says_when_it_clears(self):
        from datetime import UTC, datetime

        clears = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        rate_limits = MagicMock()
        rate_limits.is_rate_limited.return_value = True
        rate_limits.rate_limited_until.return_value = clears

        with pytest.raises(core_exceptions.TooManyRequestsError) as raised:
            strava_utils.raise_if_rate_limit_active("c", 1, rate_limits)

        assert raised.value.retry_at == clears


class TestRaiseIfRateLimitActive:
    def test_an_active_limit_refuses_the_call(self):
        rate_limits = MagicMock()
        rate_limits.is_rate_limited.return_value = True

        with pytest.raises(core_exceptions.TooManyRequestsError):
            strava_utils.raise_if_rate_limit_active("c", 1, rate_limits)

    def test_no_limit_lets_the_call_through(self):
        rate_limits = MagicMock()
        rate_limits.is_rate_limited.return_value = False

        strava_utils.raise_if_rate_limit_active("c", 1, rate_limits)


class TestIsStravaUnauthorizedError:
    def test_an_access_unauthorized_error_is_detected(self):
        assert strava_utils.is_strava_unauthorized_error(AccessUnauthorized()) is True

    def test_a_401_fault_is_detected(self):
        assert strava_utils.is_strava_unauthorized_error(_make_strava_fault(401)) is True

    def test_another_fault_is_not(self):
        assert strava_utils.is_strava_unauthorized_error(_make_strava_fault(500)) is False

    def test_a_plain_exception_is_not(self):
        assert strava_utils.is_strava_unauthorized_error(ValueError("nope")) is False


class TestHandleRejectedToken:
    def _run(self, *, unlinked: bool):
        db = MagicMock()
        sessions = MagicMock()
        sessions.return_value.__enter__.return_value = db
        with (
            pytest.MonkeyPatch.context() as patch,
        ):
            patch.setattr(strava_utils.core_database, "SessionLocal", sessions)
            unlink = Mock(return_value=unlinked)
            patch.setattr(strava_utils.user_integrations_integration, "unlink_strava_tokens_if_refresh_token", unlink)
            note = Mock(return_value=("n", "ws"))
            patch.setattr(strava_utils.notifications_integration, "create_strava_token_expired_notification", note)
            push = Mock()
            patch.setattr(strava_utils.notifications_integration, "push_notification", push)
            strava_utils.handle_rejected_token(1, "enc-refresh", ValueError("401"))
        return db, unlink, note, push

    def test_the_rejected_token_is_unlinked_and_the_user_told_in_one_commit(self):
        db, unlink, note, push = self._run(unlinked=True)

        unlink.assert_called_once_with(1, "enc-refresh", db)
        note.assert_called_once_with(1, db)
        db.commit.assert_called_once()
        push.assert_called_once_with(1, "n", "ws")

    def test_a_token_linked_since_is_left_alone_and_nobody_is_notified(self):
        db, _unlink, note, push = self._run(unlinked=False)

        db.commit.assert_not_called()
        db.rollback.assert_called_once()
        note.assert_not_called()
        push.assert_not_called()


class TestRaiseIfUnauthorized:
    def test_a_rejected_token_unlinks_the_account_and_refuses_the_call(self, monkeypatch):
        handle = Mock()
        monkeypatch.setattr(strava_utils, "handle_rejected_token", handle)

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_utils.raise_if_unauthorized(AccessUnauthorized(), 1, Mock(strava_refresh_token="enc"))

        handle.assert_called_once()
        assert handle.call_args.args[:2] == (1, "enc")

    def test_any_other_error_passes_through(self, monkeypatch):
        handle = Mock()
        monkeypatch.setattr(strava_utils, "handle_rejected_token", handle)

        strava_utils.raise_if_unauthorized(ValueError("nope"), 1, Mock(strava_refresh_token="enc"))

        handle.assert_not_called()


class TestTokenRefreshClaim:
    @pytest.fixture(autouse=True)
    def _session(self, monkeypatch):
        monkeypatch.setattr(strava_utils.core_database, "SessionLocal", lambda: MagicMock())
        monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)

    def _due(self):
        from datetime import UTC, datetime, timedelta

        return Mock(
            strava_token="t",
            strava_refresh_token="r",
            strava_client_id="c",
            strava_client_secret="s",
            strava_token_expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )

    def test_a_process_that_loses_the_claim_does_not_refresh(self, monkeypatch):
        rate_limits = MagicMock()
        rate_limits.is_rate_limited.return_value = False
        rate_limits.claim_token_refresh.return_value = False
        monkeypatch.setattr(
            strava_utils.user_integrations_integration, "get_user_integrations", Mock(return_value=self._due())
        )
        create_client = Mock()
        monkeypatch.setattr(strava_utils, "create_strava_client", create_client)

        strava_utils.refresh_user_strava_token(1, rate_limits)

        create_client.assert_not_called()

    def test_an_expired_token_is_not_used_while_another_process_refreshes_it(self, monkeypatch):
        """Calling Strava with the dead token would get a 401 and unlink a healthy account."""
        from datetime import UTC, datetime, timedelta

        rate_limits = MagicMock()
        rate_limits.is_rate_limited.return_value = False
        rate_limits.claim_token_refresh.return_value = False
        expired = self._due()
        expired.strava_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        monkeypatch.setattr(
            strava_utils.user_integrations_integration, "get_user_integrations", Mock(return_value=expired)
        )
        create_client = Mock()
        monkeypatch.setattr(strava_utils, "create_strava_client", create_client)

        with pytest.raises(core_exceptions.TooManyRequestsError) as exc_info:
            strava_utils.refresh_user_strava_token(1, rate_limits)

        create_client.assert_not_called()
        assert exc_info.value.retry_at is not None
        assert exc_info.value.retry_at > datetime.now(UTC)

    def test_an_expired_token_that_could_not_be_refreshed_is_not_used(self, monkeypatch):
        from datetime import UTC, datetime, timedelta

        rate_limits = MagicMock(spec=["is_rate_limited", "claim_token_refresh", "mark_rate_limited"])
        rate_limits.is_rate_limited.return_value = False
        rate_limits.claim_token_refresh.return_value = True
        expired = self._due()
        expired.strava_token_expires_at = datetime.now(UTC) - timedelta(hours=1)
        monkeypatch.setattr(
            strava_utils.user_integrations_integration, "get_user_integrations", Mock(return_value=expired)
        )
        client = Mock()
        client.refresh_access_token.side_effect = ValueError("strava is down")
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))

        with pytest.raises(core_exceptions.DependencyFailedError):
            strava_utils.refresh_user_strava_token(1, rate_limits)

    def test_a_refresh_another_process_just_finished_is_not_repeated(self, monkeypatch):
        """The integration is read again under the claim, and a fresh token ends the refresh."""
        from datetime import UTC, datetime, timedelta

        rate_limits = MagicMock()
        rate_limits.is_rate_limited.return_value = False
        rate_limits.claim_token_refresh.return_value = True
        fresh = self._due()
        fresh.strava_token_expires_at = datetime.now(UTC) + timedelta(hours=5)
        monkeypatch.setattr(
            strava_utils.user_integrations_integration,
            "get_user_integrations",
            Mock(side_effect=[self._due(), fresh]),
        )
        create_client = Mock()
        monkeypatch.setattr(strava_utils, "create_strava_client", create_client)

        strava_utils.refresh_user_strava_token(1, rate_limits)

        create_client.assert_not_called()

    def test_a_failed_refresh_leaves_the_claim_to_expire(self, monkeypatch):
        rate_limits = MagicMock(spec=["is_rate_limited", "claim_token_refresh", "mark_rate_limited"])
        rate_limits.is_rate_limited.return_value = False
        rate_limits.claim_token_refresh.return_value = True
        monkeypatch.setattr(
            strava_utils.user_integrations_integration, "get_user_integrations", Mock(return_value=self._due())
        )
        client = Mock()
        client.refresh_access_token.side_effect = ValueError("bad refresh token")
        monkeypatch.setattr(strava_utils, "create_strava_client", Mock(return_value=client))

        strava_utils.refresh_user_strava_token(1, rate_limits)

        rate_limits.claim_token_refresh.assert_called_once_with(1)


class TestTokenExpiryEpoch:
    def test_the_expiry_is_read_as_utc_whatever_the_server_timezone(self, monkeypatch):
        import os
        import time
        from datetime import datetime

        monkeypatch.setenv("TZ", "Pacific/Auckland")
        time.tzset()
        try:
            monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)
            integrations = Mock(
                strava_token="t",
                strava_refresh_token="r",
                strava_token_expires_at=datetime(2026, 1, 1, 0, 0, 0),
            )
            with pytest.MonkeyPatch.context() as local:
                captured = {}
                local.setattr(strava_utils, "StravaClient", lambda **kwargs: captured.update(kwargs) or MagicMock())
                strava_utils.create_strava_client(integrations)
        finally:
            monkeypatch.delenv("TZ")
            time.tzset()

        assert captured["token_expires"] == 1767225600
        assert os.environ.get("TZ") is None
