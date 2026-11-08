"""The profile service commits what the account-security surface only stages."""

from unittest.mock import MagicMock, patch

import pytest

import modules.users.users.schema as users_schema
import modules.users.users_profile.service as profile_service

_ACCOUNT_SECURITY = "modules.users.users_profile.service.account_security_integration"


@pytest.fixture(autouse=True)
def _breach_check_off():
    with patch(
        "modules.users.users_profile.service.server_settings_integration.get_server_settings",
        return_value=MagicMock(password_breach_check_enabled=False),
    ):
        yield


def test_changing_the_password_stages_through_account_security_then_commits(mock_db):
    change = users_schema.UserEditPassword(
        password="new-password-1", step_up={"current_password": "old-password"}, revoke_other_sessions=True
    )
    store = MagicMock()
    with patch(_ACCOUNT_SECURITY) as account_security:
        profile_service.change_password(5, change, "sid", store, mock_db)

    account_security.change_own_password.assert_called_once()
    assert account_security.change_own_password.call_args.kwargs["current_session_id"] == "sid"
    mock_db.commit.assert_called_once()


def test_changing_the_password_revokes_other_sessions_unless_the_client_opts_out(mock_db):
    change = users_schema.UserEditPassword(password="new-password-1", step_up={"current_password": "old-password"})
    with patch(_ACCOUNT_SECURITY) as account_security:
        profile_service.change_password(5, change, "sid", MagicMock(), mock_db)

    assert account_security.change_own_password.call_args.kwargs["revoke_other_sessions"] is True
