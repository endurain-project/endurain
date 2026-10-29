"""Tests for authentication token-selection and refresh-token dependencies."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import modules.auth.access_tokens.service as access_tokens_service
import modules.auth.authentication.dependencies as authentication_dependencies


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


def test_get_token_rejects_missing_access_token():
    with pytest.raises(core_exceptions.DomainError) as exc_info:
        authentication_dependencies.get_token(None, None, "web", access_tokens_service.TokenType.ACCESS)
    assert exc_info.value.status_code == 401


def test_access_expiration_accepts_valid_token(token_manager, sample_user_read):
    _, access_token = token_manager.create_token(
        "session-id", sample_user_read, access_tokens_service.TokenType.ACCESS, timedelta(minutes=15)
    )
    token_manager.validate_access_expiration_logged(access_token)


def test_refresh_claims_are_extracted(token_manager, sample_user_read):
    _, refresh_token = token_manager.create_token(
        "session-id", sample_user_read, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
    )
    assert authentication_dependencies.get_sub_from_refresh_token(refresh_token, token_manager) == sample_user_read.id
    assert authentication_dependencies.get_sid_from_refresh_token(refresh_token, token_manager) == "session-id"


def test_refresh_expiry_is_the_tokens_own_exp_claim(token_manager, sample_user_read):
    """The rotated record is kept until this instant, so it has to be the token's, not the policy's."""
    exp, refresh_token = token_manager.create_token(
        "session-id", sample_user_read, access_tokens_service.TokenType.REFRESH, timedelta(days=30)
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
        "session-id", sample_user_read, access_tokens_service.TokenType.REFRESH, timedelta(days=1)
    )
    authentication_dependencies.validate_refresh_token(refresh_token, token_manager)


def test_get_and_return_refresh_token_preserves_value():
    assert authentication_dependencies.get_and_return_refresh_token("refresh") == "refresh"


def test_clear_cookie_handler_clears_refresh_cookies(monkeypatch):
    response = MagicMock()
    monkeypatch.setattr(authentication_dependencies.core_config.settings, "ENVIRONMENT", "development")
    authentication_dependencies.clear_refresh_token_cookies(response, environment="development")
    assert response.delete_cookie.call_count == len(authentication_dependencies.REFRESH_TOKEN_COOKIE_CLEAR_PATHS)
