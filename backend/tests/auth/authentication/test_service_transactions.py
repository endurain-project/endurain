"""The authentication service commits what the session and IdP surfaces only stage."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.config as core_config
import core.exceptions as core_exceptions
import modules.auth.authentication.refresh_service as authentication_service_refresh_service
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.identity_provider_links.crud as identity_links_crud
from tests._helpers.db import create_sqlite_session

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
        patch(f"{_SERVICE}.users_integration.get_user", return_value=SimpleNamespace(id=1, active=True)),
        patch(f"{_SERVICE}.users_integration.require_active_user"),
        patch("modules.auth.authentication.token_service.create_tokens", return_value=tokens),
        patch(
            "modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token"
        ) as store,
        patch(
            f"{_SERVICE}.sessions_integration.edit_session",
            return_value=SimpleNamespace(expires_at=datetime(2027, 1, 1, tzinfo=UTC)),
        ),
        patch("modules.auth.authentication.refresh_service.identity_providers_integration.request_idp_token_refresh"),
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
        patch(f"{_SERVICE}.users_integration.get_user", return_value=SimpleNamespace(id=1, active=True)),
        patch(f"{_SERVICE}.users_integration.require_active_user"),
        patch("modules.auth.authentication.token_service.create_tokens", return_value=tokens),
        patch("modules.auth.authentication.refresh_service.rotated_refresh_tokens_integration.store_rotated_token"),
        patch(f"{_SERVICE}.sessions_integration.edit_session", return_value=SimpleNamespace(expires_at=session_expiry)),
        patch("modules.auth.authentication.refresh_service.identity_providers_integration.request_idp_token_refresh"),
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
        patch(f"{_SERVICE}.identity_providers_integration.read_end_session", return_value=None),
    ):
        authentication_service.logout("sid", "rt", 1, hasher, auth_constants.ClientType.WEB, mock_db)

    delete_session.assert_called_once_with("sid", 1, mock_db)
    mock_db.commit.assert_called_once()


def test_a_logout_leaves_the_identity_provider_tokens_of_the_users_other_sessions_alone():
    db = create_sqlite_session()
    for session_id, idp_id in (("sid", 3), ("other-device", 3), ("other-provider", 4)):
        identity_links_crud.create_idp_session_token(session_id, 1, idp_id, "encrypted", None, db)
    db.commit()
    hasher = MagicMock()
    hasher.verify_password.return_value = True
    with (
        patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
        patch(f"{_SERVICE}.sessions_integration.delete_session"),
        patch(f"{_SERVICE}.identity_providers_integration.read_end_session", return_value=None),
    ):
        authentication_service.logout("sid", "rt", 1, hasher, auth_constants.ClientType.WEB, db)

    remaining = {
        row.session_id: row.refresh_token for row in identity_links_crud.get_idp_session_tokens_page(0, 10, db)
    }
    assert remaining == {"sid": "encrypted", "other-device": "encrypted", "other-provider": "encrypted"}
    db.close()


class TestLogoutEndsTheProviderSessionLast:
    """The Endurain session is ended and committed before the provider's endpoint is resolved."""

    @staticmethod
    def _logout(client_type, db, *, events, end_session="request", url="https://idp.example.com/out"):
        hasher = MagicMock()
        hasher.verify_password.return_value = True
        db.commit.side_effect = lambda: events.append("commit")
        with (
            patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
            patch(f"{_SERVICE}.sessions_integration.delete_session", side_effect=lambda *a: events.append("delete")),
            patch(
                f"{_SERVICE}.identity_providers_integration.read_end_session",
                side_effect=lambda *a: events.append("read") or end_session,
            ) as read,
            patch(
                f"{_SERVICE}.identity_providers_integration.end_session_url",
                side_effect=lambda *a: events.append("resolve") or url,
            ) as resolve,
        ):
            result = authentication_service.logout("sid", "rt", 1, hasher, client_type, db)
        return result, read, resolve

    def test_the_ids_are_read_before_the_session_is_deleted_and_the_endpoint_resolved_after_the_commit(self, mock_db):
        events: list[str] = []

        result, read, resolve = self._logout(auth_constants.ClientType.WEB, mock_db, events=events)

        assert events == ["read", "delete", "commit", "resolve"]
        assert result == "https://idp.example.com/out"
        read.assert_called_once_with("sid", mock_db)
        resolve.assert_called_once_with("request", f"{core_config.settings.ENDURAIN_HOST}/login")

    def test_a_mobile_client_gets_no_return_address(self, mock_db):
        _, _, resolve = self._logout(auth_constants.ClientType.MOBILE, mock_db, events=[])

        resolve.assert_called_once_with("request", None)

    def test_a_session_signed_in_without_a_provider_resolves_nothing(self, mock_db):
        events: list[str] = []

        result, _, resolve = self._logout(auth_constants.ClientType.WEB, mock_db, events=events, end_session=None)

        assert result is None
        assert events == ["read", "delete", "commit"]
        resolve.assert_not_called()

    def test_a_provider_without_an_endpoint_leaves_the_url_null(self, mock_db):
        result, _, _ = self._logout(auth_constants.ClientType.WEB, mock_db, events=[], url=None)

        assert result is None
