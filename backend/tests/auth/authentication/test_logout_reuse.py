"""Logging out with a refresh token that an earlier refresh rotated is a reuse, as it is at refresh."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants

_SERVICE = "modules.auth.authentication.service"
_SESSION_ID = uuid.UUID(int=7)
_FAMILY_ID = uuid.UUID(int=8)
_USER_ID = uuid.UUID(int=1)


def _session():
    return SimpleNamespace(id=_SESSION_ID, token_family_id=_FAMILY_ID, refresh_token="digest")


def _logout(mock_db, *, matches: bool, reuse: tuple[bool, bool]):
    with (
        patch(f"{_SERVICE}.sessions_integration.get_session_by_id_not_expired", return_value=_session()),
        patch(f"{_SERVICE}.sessions_integration.verify_refresh_token", return_value=matches),
        patch(f"{_SERVICE}.rotated_refresh_tokens_integration.check_token_reuse", return_value=reuse) as check,
        patch(f"{_SERVICE}.authentication_refresh_service.end_session_on_reuse") as end_family,
        patch(f"{_SERVICE}.sessions_integration.delete_session") as delete_session,
        patch(f"{_SERVICE}.identity_providers_integration.read_end_session", return_value=None),
    ):
        result = authentication_service.logout(
            _SESSION_ID, "old-token", _USER_ID, auth_constants.ClientType.MOBILE, "203.0.113.5", "agent", mock_db
        )
    return result, check, end_family, delete_session


def test_a_rotated_token_used_outside_its_grace_window_ends_the_token_family(mock_db):
    result, check, end_family, delete_session = _logout(mock_db, matches=False, reuse=(True, False))

    assert result is None
    check.assert_called_once_with("old-token", mock_db, ip_address="203.0.113.5", user_agent="agent")
    end_family.assert_called_once_with(_USER_ID, _FAMILY_ID, mock_db)
    delete_session.assert_not_called()


@pytest.mark.parametrize("reuse", [(True, True), (False, False)])
def test_a_retry_in_the_grace_window_or_an_unknown_token_ends_nothing(mock_db, reuse):
    result, _check, end_family, delete_session = _logout(mock_db, matches=False, reuse=reuse)

    assert result is None
    end_family.assert_not_called()
    delete_session.assert_not_called()


def test_the_current_token_ends_its_session_without_a_reuse_check(mock_db):
    _result, check, end_family, delete_session = _logout(mock_db, matches=True, reuse=(False, False))

    check.assert_not_called()
    end_family.assert_not_called()
    delete_session.assert_called_once_with(_SESSION_ID, _USER_ID, mock_db)
