"""The authentication service commits what the session and IdP surfaces only stage."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.refresh_service as authentication_service_refresh_service
import modules.auth.authentication.service as authentication_service

_SERVICE = "modules.auth.authentication.service"
_OLD_EXP = datetime(2026, 11, 28, tzinfo=UTC)


def _session(**overrides):
    values = {
        "user_id": 1,
        "token_family_id": "family",
        "refresh_token": "hash",
        "csrf_token_hash": None,
        "rotation_count": 0,
        "id": "sid",
    }
    return SimpleNamespace(**{**values, **overrides})


def test_a_reused_refresh_token_keeps_the_family_invalidated_although_the_request_is_refused(mock_db):
    with (
        patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
        patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
        patch(
            "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
            return_value=(True, False),
        ),
        patch(f"{_SERVICE}.sessions_integration.invalidate_token_family") as invalidate,
        pytest.raises(core_exceptions.UnauthenticatedError),
    ):
        authentication_service_refresh_service.refresh_token(
            "127.0.0.1", "agent", 1, "sid", "old", _OLD_EXP, MagicMock(), MagicMock(), "mobile", mock_db
        )

    invalidate.assert_called_once_with("family", mock_db)
    mock_db.commit.assert_called_once()


def test_a_rotation_records_the_presented_tokens_own_expiry(mock_db):
    """Reuse detection keeps the record until the old token could no longer be presented."""
    hasher = MagicMock()
    hasher.verify_password.return_value = True
    tokens = ("sid", datetime(2026, 11, 1, tzinfo=UTC), "at", datetime(2026, 12, 1, tzinfo=UTC), "rt", "csrf")
    with (
        patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
        patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
        patch(
            "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
            return_value=(False, False),
        ),
        patch(f"{_SERVICE}.users_integration.get_user", return_value=SimpleNamespace(id=1)),
        patch(f"{_SERVICE}.users_integration.require_active_user"),
        patch("modules.auth.authentication.token_service.create_tokens", return_value=tokens),
        patch(
            "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token"
        ) as store,
        patch(
            f"{_SERVICE}.sessions_integration.edit_session",
            return_value=SimpleNamespace(expires_at=datetime(2027, 1, 1, tzinfo=UTC)),
        ),
        patch(f"{_SERVICE}.identity_providers_integration.request_idp_token_refresh"),
    ):
        authentication_service_refresh_service.refresh_token(
            "127.0.0.1", "agent", 1, "sid", "old", _OLD_EXP, hasher, MagicMock(), "mobile", mock_db
        )

    assert store.call_args.kwargs["refresh_token_exp"] == _OLD_EXP


def test_a_rotation_reports_the_sessions_capped_expiry_for_the_body_and_the_cookie(mock_db):
    """The absolute session timeout can end the session before the new refresh token expires."""
    hasher = MagicMock()
    hasher.verify_password.return_value = True
    session_expiry = datetime.now(UTC) + timedelta(hours=2)
    tokens = ("sid", datetime.now(UTC) + timedelta(minutes=15), "at", datetime.now(UTC) + timedelta(days=7), "rt", "c")
    with (
        patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
        patch(f"{_SERVICE}.server_settings_integration.get_session_policy"),
        patch(f"{_SERVICE}.sessions_integration.validate_session_timeout"),
        patch(
            "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.check_token_reuse",
            return_value=(False, False),
        ),
        patch(f"{_SERVICE}.users_integration.get_user", return_value=SimpleNamespace(id=1)),
        patch(f"{_SERVICE}.users_integration.require_active_user"),
        patch("modules.auth.authentication.token_service.create_tokens", return_value=tokens),
        patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token"),
        patch(f"{_SERVICE}.sessions_integration.edit_session", return_value=SimpleNamespace(expires_at=session_expiry)),
        patch(f"{_SERVICE}.identity_providers_integration.request_idp_token_refresh"),
    ):
        outcome = authentication_service_refresh_service.refresh_token(
            "127.0.0.1", "agent", 1, "sid", "old", _OLD_EXP, hasher, MagicMock(), "web", mock_db
        )

    assert outcome.body.refresh_token_expires_in == pytest.approx(2 * 3600, abs=2)
    assert outcome.refresh_cookie.expires_at == session_expiry


def test_logout_commits_the_session_deletion(mock_db):
    hasher = MagicMock()
    hasher.verify_password.return_value = True
    with (
        patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
        patch(f"{_SERVICE}.sessions_integration.delete_session") as delete_session,
        patch(f"{_SERVICE}.identity_providers_integration.clear_all_idp_tokens"),
    ):
        authentication_service.logout("sid", "rt", 1, hasher, mock_db)

    delete_session.assert_called_once_with("sid", 1, mock_db)
    assert mock_db.commit.call_count == 2
