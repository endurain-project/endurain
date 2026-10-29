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


def test_starting_a_browser_link_commits_the_staged_state_before_building_the_provider_url(mock_db):
    staged = MagicMock(browser_binding="binding-secret")
    order = MagicMock()
    order.attach_mock(mock_db.commit, "commit")
    with patch(_ACCOUNT_SECURITY) as account_security:
        account_security.stage_browser_idp_link.return_value = staged
        account_security.browser_flow_authorization_url.return_value = "https://idp.example.com/auth"
        order.attach_mock(account_security.browser_flow_authorization_url, "build_url")
        start = profile_service.start_identity_provider_link("token", 2, "/settings", "10.0.0.1", mock_db)

    account_security.stage_browser_idp_link.assert_called_once_with("token", 2, "/settings", "10.0.0.1", mock_db)
    account_security.browser_flow_authorization_url.assert_called_once_with(staged)
    assert [call[0] for call in order.mock_calls] == ["commit", "build_url"]
    assert start.authorization_url == "https://idp.example.com/auth"
    assert start.browser_binding == "binding-secret"
