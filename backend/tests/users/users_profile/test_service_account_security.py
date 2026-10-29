"""The profile service commits what the account-security surface only stages."""

from unittest.mock import MagicMock, patch

import modules.users.users.schema as users_schema
import modules.users.users_profile.service as profile_service

_ACCOUNT_SECURITY = "modules.users.users_profile.service.account_security_integration"


def test_changing_the_password_stages_through_account_security_then_commits(mock_db):
    change = users_schema.UsersEditPassword(
        current_password="old-password", password="new-password-1", mfa_code=None, revoke_other_sessions=True
    )
    store = MagicMock()
    with patch(_ACCOUNT_SECURITY) as account_security:
        profile_service.change_password(5, change, "sid", store, mock_db)

    account_security.change_own_password.assert_called_once()
    assert account_security.change_own_password.call_args.kwargs["current_session_id"] == "sid"
    mock_db.commit.assert_called_once()


def test_starting_a_browser_link_commits_the_claimed_link_token_and_oauth_state(mock_db):
    with patch(_ACCOUNT_SECURITY) as account_security:
        account_security.start_browser_idp_link.return_value = "start"
        start = profile_service.start_identity_provider_link("token", 2, "/settings", "10.0.0.1", mock_db)

    assert start == "start"
    mock_db.commit.assert_called_once()
