"""Tests for authentication token-selection and refresh-token dependencies."""

import uuid
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import modules.auth.access_tokens.service as access_tokens_service
import modules.auth.authentication.dependencies as authentication_dependencies
from modules.auth.constants import ClientType


def test_get_token_selects_access_header_and_client_refresh_source():
    assert (
        authentication_dependencies.get_token("access", "cookie", "web", access_tokens_service.TokenType.ACCESS)
        == "access"
    )
    assert (
        authentication_dependencies.get_token(None, "cookie", "web", access_tokens_service.TokenType.REFRESH)
        == "cookie"
    )
    assert (
        authentication_dependencies.get_token("refresh", None, "mobile", access_tokens_service.TokenType.REFRESH)
        == "refresh"
    )


def test_get_token_rejects_a_missing_mobile_refresh_token_naming_the_body():
    with pytest.raises(core_exceptions.InvalidTokenError) as exc_info:
        authentication_dependencies.get_token(None, None, "mobile", access_tokens_service.TokenType.REFRESH)
    assert exc_info.value.detail == "Refresh token missing from request body"


def test_get_token_rejects_missing_access_token():
    with pytest.raises(core_exceptions.DomainError) as exc_info:
        authentication_dependencies.get_token(None, None, "web", access_tokens_service.TokenType.ACCESS)
    assert exc_info.value.status_code == 401


def test_access_expiration_accepts_valid_token(token_manager, sample_user_read):
    _, access_token = token_manager.create_token(
        "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.ACCESS, timedelta(minutes=15)
    )
    token_manager.validate_access_expiration_logged(access_token)


def test_refresh_claims_are_extracted(token_manager, sample_user_read):
    _, refresh_token = token_manager.create_token(
        "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
    )
    assert authentication_dependencies.get_sub_from_refresh_token(refresh_token, token_manager) == sample_user_read.id
    assert authentication_dependencies.get_sid_from_refresh_token(refresh_token, token_manager) == "session-id"


def test_the_refresh_subject_is_the_user_uuid(token_manager, sample_user_read):
    _, refresh_token = token_manager.create_token(
        "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
    )

    subject = authentication_dependencies.get_sub_from_refresh_token(refresh_token, token_manager)

    assert isinstance(subject, uuid.UUID)


@pytest.mark.parametrize("subject", [7, "7", "not-a-user-id", ""])
def test_a_refresh_subject_that_is_not_a_user_uuid_is_refused(token_manager, sample_user_read, subject):
    """A token from before the upgrade carries a decimal subject and is refused as unauthenticated."""
    user = SimpleNamespace(id=subject, access_type=sample_user_read.access_type)
    _, refresh_token = token_manager.create_token(
        "session-id", user, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
    )

    with pytest.raises(core_exceptions.InvalidTokenError):
        authentication_dependencies.get_sub_from_refresh_token(refresh_token, token_manager)


def test_refresh_expiry_is_the_tokens_own_exp_claim(token_manager, sample_user_read):
    """The rotated record is kept until this instant, so it has to be the token's, not the policy's."""
    exp, refresh_token = token_manager.create_token(
        "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(days=30)
    )
    assert authentication_dependencies.get_exp_from_refresh_token(refresh_token, token_manager) == exp.replace(
        microsecond=0
    )


def test_refresh_expiry_must_be_an_integer_claim():
    token_manager = MagicMock()
    token_manager.get_token_claim.return_value = "soon"
    with pytest.raises(core_exceptions.UnauthenticatedError):
        authentication_dependencies.get_exp_from_refresh_token("refresh", token_manager)


def test_validate_refresh_token_accepts_a_valid_token(token_manager, sample_user_read):
    _, refresh_token = token_manager.create_token(
        "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
    )
    authentication_dependencies.validate_refresh_token(refresh_token, token_manager)


def test_validate_refresh_token_clears_the_cookie_of_an_expired_token(token_manager, sample_user_read):
    _, refresh_token = token_manager.create_token(
        "session-id",
        sample_user_read,
        ClientType.WEB,
        access_tokens_service.TokenType.REFRESH,
        timedelta(seconds=-core_jwt_keys.CLOCK_LEEWAY_SECONDS - 60),
    )
    with pytest.raises(authentication_dependencies.ClearRefreshTokenCookieError):
        authentication_dependencies.validate_refresh_token(refresh_token, token_manager)


def test_validate_refresh_token_clears_the_cookie_of_an_access_token(token_manager, sample_user_read):
    _, access_token = token_manager.create_token(
        "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.ACCESS, timedelta(days=1)
    )
    with pytest.raises(authentication_dependencies.ClearRefreshTokenCookieError):
        authentication_dependencies.validate_refresh_token(access_token, token_manager)


def test_get_and_return_refresh_token_preserves_value():
    assert authentication_dependencies.get_and_return_refresh_token("refresh") == "refresh"


def test_clear_cookie_handler_clears_refresh_cookies(monkeypatch):
    response = MagicMock()
    monkeypatch.setattr(authentication_dependencies.core_config.settings, "ENVIRONMENT", "development")
    authentication_dependencies.clear_refresh_token_cookies(response, environment="development")
    response.delete_cookie.assert_called_once()


def test_refresh_token_claim_readers_follow_validation():
    """A route using a refresh-token claim reader declares ``validate_refresh_token`` before it.

    The readers check only the signature, so they rely on the validating dependency having run first.
    """
    import modules.auth.authentication.public_router as public_router

    readers = {
        authentication_dependencies.get_sub_from_refresh_token,
        authentication_dependencies.get_sid_from_refresh_token,
        authentication_dependencies.get_exp_from_refresh_token,
    }
    checked = 0
    for route in public_router.router.routes:
        calls = [dependency.call for dependency in route.dependant.dependencies]
        if not readers.intersection(calls):
            continue
        checked += 1
        assert authentication_dependencies.validate_refresh_token in calls, route.path
        validation_index = calls.index(authentication_dependencies.validate_refresh_token)
        for reader in readers.intersection(calls):
            assert validation_index < calls.index(reader), f"{route.path} reads claims before validating"
    assert checked >= 1


class TestGetLogoutTarget:
    """A logout names a session only from a usable refresh token; any other token names none."""

    @staticmethod
    def _target(token_manager, *, cookie=None, body_token=None, client_type=ClientType.WEB):
        return authentication_dependencies.get_logout_target(body_token, cookie, client_type, token_manager)

    def test_a_valid_web_token_names_its_session(self, token_manager, sample_user_read):
        _, token = token_manager.create_token(
            "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
        )

        assert self._target(token_manager, cookie=token) == authentication_dependencies.LogoutTarget(
            sample_user_read.id, "session-id", token
        )

    def test_a_token_with_a_decimal_subject_names_no_session(self, token_manager, sample_user_read):
        user = SimpleNamespace(id=7, access_type=sample_user_read.access_type)
        _, token = token_manager.create_token(
            "session-id", user, ClientType.WEB, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
        )

        assert self._target(token_manager, cookie=token) is None

    def test_a_valid_mobile_token_is_read_from_the_request_body(self, token_manager, sample_user_read):
        _, token = token_manager.create_token(
            "session-id",
            sample_user_read,
            ClientType.MOBILE,
            access_tokens_service.TokenType.REFRESH,
            timedelta(days=1),
        )

        target = self._target(token_manager, body_token=token, client_type=ClientType.MOBILE)

        assert target is not None
        assert target.session_id == "session-id"

    def test_a_missing_token_names_no_session(self, token_manager):
        assert self._target(token_manager) is None
        assert self._target(token_manager, client_type=ClientType.MOBILE) is None

    def test_a_malformed_token_names_no_session(self, token_manager):
        assert self._target(token_manager, cookie="not-a-jwt") is None

    def test_an_expired_token_names_no_session(self, token_manager, sample_user_read):
        _, token = token_manager.create_token(
            "session-id",
            sample_user_read,
            ClientType.WEB,
            access_tokens_service.TokenType.REFRESH,
            timedelta(seconds=-120),
        )

        assert self._target(token_manager, cookie=token) is None

    def test_an_access_token_names_no_session(self, token_manager, sample_user_read):
        _, token = token_manager.create_token(
            "session-id", sample_user_read, ClientType.WEB, access_tokens_service.TokenType.ACCESS, timedelta(days=1)
        )

        assert self._target(token_manager, cookie=token) is None
