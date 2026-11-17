"""Tests for the opt-in breached-password check against the Have I Been Pwned range API."""

import hashlib
import logging
from unittest.mock import MagicMock, patch

import httpx2
import pytest

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.password_breach as credentials_password_breach
import modules.auth.credentials.service as credentials_service

_PASSWORD = "correct horse battery staple"
_DIGEST = hashlib.sha1(_PASSWORD.encode(), usedforsecurity=False).hexdigest().upper()
_PREFIX, _SUFFIX = _DIGEST[:5], _DIGEST[5:]


def _response(body: str, status: int = 200) -> httpx2.Response:
    return httpx2.Response(status, text=body, request=httpx2.Request("GET", credentials_password_breach.RANGE_API_URL))


def _get(response: httpx2.Response | Exception):
    if isinstance(response, Exception):
        return patch.object(credentials_password_breach.httpx2, "get", side_effect=response)
    return patch.object(credentials_password_breach.httpx2, "get", return_value=response)


class TestIsBreached:
    def test_suffix_found_is_breached(self):
        with _get(_response(f"0018A45C4D1DEF81644B54AB7F969B88D65:3\r\n{_SUFFIX}:42\r\n")):
            assert credentials_password_breach.is_breached(_PASSWORD) is True

    def test_suffix_absent_is_allowed(self):
        with _get(_response("0018A45C4D1DEF81644B54AB7F969B88D65:3\r\n")):
            assert credentials_password_breach.is_breached(_PASSWORD) is False

    def test_padding_entry_with_count_zero_is_ignored(self):
        with _get(_response(f"{_SUFFIX}:0\r\n")):
            assert credentials_password_breach.is_breached(_PASSWORD) is False

    def test_only_the_prefix_is_sent(self):
        with _get(_response("")) as get:
            credentials_password_breach.is_breached(_PASSWORD)
        (url,) = get.call_args.args
        assert url == f"{credentials_password_breach.RANGE_API_URL}{_PREFIX}"
        assert _SUFFIX not in repr(get.call_args)
        assert _PASSWORD not in repr(get.call_args)
        assert get.call_args.kwargs["headers"]["Add-Padding"] == "true"
        assert get.call_args.kwargs["timeout"] == credentials_password_breach.REQUEST_TIMEOUT_SECONDS
        assert get.call_args.kwargs["follow_redirects"] is False

    def test_password_is_hashed_in_nfc_form(self):
        composed, decomposed = "café-au-lait-noir", "café-au-lait-noir"
        with _get(_response("")) as get:
            credentials_password_breach.is_breached(decomposed)
        digest = hashlib.sha1(composed.encode(), usedforsecurity=False).hexdigest().upper()
        assert get.call_args.args[0].endswith(digest[:5])

    @pytest.mark.parametrize(
        "failure",
        [
            httpx2.ReadTimeout("slow"),
            httpx2.ConnectError("down"),
            _response("", status=503),
        ],
    )
    def test_failure_allows_the_password_and_warns(self, failure, caplog):
        with caplog.at_level(logging.WARNING), _get(failure):
            assert credentials_password_breach.is_breached(_PASSWORD) is False
        assert any(record.levelno == logging.WARNING for record in caplog.records)
        logged = " ".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
        assert _PASSWORD not in logged
        assert _DIGEST not in logged
        assert _PREFIX not in logged


class TestRejectBreachedPassword:
    def _settings(self, enabled: bool) -> MagicMock:
        return MagicMock(password_breach_check_enabled=enabled)

    def test_disabled_does_not_call_out_or_end_the_transaction(self):
        db = MagicMock()
        with (
            patch.object(credentials_service.credentials_password_breach, "is_breached") as is_breached,
        ):
            credentials_service.reject_breached_password(self._settings(False), _PASSWORD, db)
        is_breached.assert_not_called()
        db.rollback.assert_not_called()

    def test_enabled_refuses_a_breached_password_after_ending_the_transaction(self):
        db = MagicMock()
        order: list[str] = []
        db.rollback.side_effect = lambda: order.append("rollback")
        with (
            patch.object(
                credentials_service.credentials_password_breach,
                "is_breached",
                side_effect=lambda _p: order.append("call") or True,
            ),
            pytest.raises(credentials_contracts.PasswordBreachedError),
        ):
            credentials_service.reject_breached_password(self._settings(True), _PASSWORD, db)
        assert order == ["rollback", "call"]

    def test_enabled_allows_a_password_that_is_not_breached(self):
        with (
            patch.object(credentials_service.credentials_password_breach, "is_breached", return_value=False),
        ):
            credentials_service.reject_breached_password(self._settings(True), _PASSWORD, MagicMock())


class TestBreachedError:
    def test_code_and_status(self):
        error = credentials_contracts.PasswordBreachedError
        assert issubclass(error, credentials_contracts.PasswordPolicyError)
        assert error.code == "password-breached"
        assert error.status_code == 422
