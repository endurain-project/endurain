"""The users service commits what the account-security surface only stages."""

from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.users.users.service as users_service

_ACCOUNT_SECURITY = "modules.users.users.service.account_security_integration"


def test_an_administrator_password_change_commits(mock_db):
    with patch(_ACCOUNT_SECURITY) as account_security:
        users_service.change_user_password(4, "new-password-1", 9, mock_db)

    account_security.change_managed_user_password.assert_called_once_with(4, "new-password-1", mock_db)
    mock_db.commit.assert_called_once()


def test_an_administrator_unlink_commits(mock_db):
    with patch(_ACCOUNT_SECURITY) as account_security:
        users_service.unlink_identity_provider(4, 9, 8, mock_db)

    account_security.admin_delete_identity_provider_link.assert_called_once_with(4, 9, mock_db)
    mock_db.commit.assert_called_once()


def test_an_administrator_cannot_change_their_own_password_without_step_up(mock_db):
    with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
        users_service.change_user_password(4, "new-password-1", 4, mock_db)

    account_security.change_managed_user_password.assert_not_called()
    mock_db.commit.assert_not_called()


def test_an_administrator_cannot_unlink_their_own_identity_provider_without_step_up(mock_db):
    with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
        users_service.unlink_identity_provider(4, 9, 4, mock_db)

    account_security.admin_delete_identity_provider_link.assert_not_called()
    mock_db.commit.assert_not_called()
