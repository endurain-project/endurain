"""The users service commits what the account-security surface only stages."""

from unittest.mock import patch

import modules.users.users.service as users_service

_ACCOUNT_SECURITY = "modules.users.users.service.account_security_integration"


def test_an_administrator_password_change_commits(mock_db):
    with patch(_ACCOUNT_SECURITY) as account_security:
        users_service.change_user_password(4, "new-password-1", mock_db)

    account_security.change_managed_user_password.assert_called_once_with(4, "new-password-1", mock_db)
    mock_db.commit.assert_called_once()


def test_an_administrator_unlink_commits(mock_db):
    with patch(_ACCOUNT_SECURITY) as account_security:
        users_service.unlink_identity_provider(4, 9, mock_db)

    account_security.admin_delete_identity_provider_link.assert_called_once_with(4, 9, mock_db)
    mock_db.commit.assert_called_once()
