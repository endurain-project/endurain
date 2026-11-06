"""The users service commits what the account-security surface only stages, after the administrator's step-up."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_ACCOUNT_SECURITY = "modules.users.users.service.account_security_integration"
_ACTION = identity_providers_constants.StepUpAction


def _password() -> users_schema.UserAdminEditPassword:
    return users_schema.UserAdminEditPassword(password="new-password-1", current_password="admin-password")


def _failing_step_up(account_security):
    account_security.verify_step_up.side_effect = core_exceptions.PermissionDeniedError("wrong password")


class TestAdministratorPasswordChange:
    def test_commits_after_the_step_up_of_the_administrator(self, mock_db):
        store = MagicMock()
        attributes = _password()
        with patch(_ACCOUNT_SECURITY) as account_security:
            order = MagicMock()
            order.attach_mock(account_security.verify_step_up, "step_up")
            order.attach_mock(account_security.change_managed_user_password, "change")
            order.attach_mock(mock_db.commit, "commit")

            users_service.change_user_password(4, attributes, 9, "sid-9", store, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "change", "commit"]
        account_security.verify_step_up.assert_called_once_with(
            attributes, 9, "sid-9", _ACTION.ADMIN_CREDENTIAL_RESET, store, mock_db
        )
        account_security.change_managed_user_password.assert_called_once_with(4, "new-password-1", mock_db)

    def test_a_failed_step_up_changes_nothing(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            _failing_step_up(account_security)
            users_service.change_user_password(4, _password(), 9, "sid-9", MagicMock(), mock_db)

        account_security.change_managed_user_password.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_an_administrator_cannot_change_their_own_password_here(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.change_user_password(4, _password(), 4, "sid-4", MagicMock(), mock_db)

        account_security.verify_step_up.assert_not_called()
        account_security.change_managed_user_password.assert_not_called()
        mock_db.commit.assert_not_called()


class TestAdministratorUnlink:
    def test_commits_after_the_step_up_of_the_administrator(self, mock_db):
        store = MagicMock()
        step_up = users_schema.StepUpVerification(current_password="admin-password")
        with patch(_ACCOUNT_SECURITY) as account_security:
            order = MagicMock()
            order.attach_mock(account_security.verify_step_up, "step_up")
            order.attach_mock(account_security.admin_delete_identity_provider_link, "unlink")
            order.attach_mock(mock_db.commit, "commit")

            users_service.unlink_identity_provider(4, 9, 8, "sid-8", step_up, store, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "unlink", "commit"]
        account_security.verify_step_up.assert_called_once_with(
            step_up, 8, "sid-8", _ACTION.ADMIN_IDP_UNLINK, store, mock_db
        )
        account_security.admin_delete_identity_provider_link.assert_called_once_with(4, 9, mock_db)

    def test_a_failed_step_up_changes_nothing(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            _failing_step_up(account_security)
            users_service.unlink_identity_provider(
                4, 9, 8, "sid-8", users_schema.StepUpVerification(), MagicMock(), mock_db
            )

        account_security.admin_delete_identity_provider_link.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_an_administrator_cannot_unlink_their_own_identity_provider_here(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.unlink_identity_provider(
                4, 9, 4, "sid-4", users_schema.StepUpVerification(), MagicMock(), mock_db
            )

        account_security.verify_step_up.assert_not_called()
        account_security.admin_delete_identity_provider_link.assert_not_called()
        mock_db.commit.assert_not_called()
