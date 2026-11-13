"""The users service commits what the account-security surface only stages, after the administrator's step-up."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.schema as auth_schema
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_U4, _U8, _U9, _IDP_ID = (uuid.UUID(int=n) for n in (4, 8, 9, 19))
_SID_4 = uuid.UUID(int=104)
_SID_8 = uuid.UUID(int=108)
_SID_9 = uuid.UUID(int=109)
_ACCOUNT_SECURITY = "modules.users.users.service.account_security_integration"
_ACTION = identity_providers_constants.StepUpAction


@pytest.fixture(autouse=True)
def _no_breach_check(monkeypatch):
    monkeypatch.setattr(users_service.credentials_integration, "reject_breached_password", lambda *_args: None)
    monkeypatch.setattr(users_service.server_settings_integration, "get_server_settings", lambda db: MagicMock())


def _password() -> users_schema.UserAdminEditPassword:
    return users_schema.UserAdminEditPassword(password="new-password-1", step_up={"current_password": "admin-password"})


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

            users_service.change_user_password(_U4, attributes, _U9, _SID_9, store, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "change", "commit"]
        account_security.verify_step_up.assert_called_once_with(
            attributes.step_up, _U9, _SID_9, _ACTION.ADMIN_CREDENTIAL_RESET, store, mock_db
        )
        account_security.change_managed_user_password.assert_called_once_with(_U4, "new-password-1", mock_db)

    def test_a_failed_step_up_changes_nothing(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            _failing_step_up(account_security)
            users_service.change_user_password(_U4, _password(), _U9, _SID_9, MagicMock(), mock_db)

        account_security.change_managed_user_password.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_an_administrator_cannot_change_their_own_password_here(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.change_user_password(_U4, _password(), _U4, _SID_4, MagicMock(), mock_db)

        account_security.verify_step_up.assert_not_called()
        account_security.change_managed_user_password.assert_not_called()
        mock_db.commit.assert_not_called()


def _step_up_request() -> auth_schema.StepUpRequest:
    return auth_schema.StepUpRequest(step_up={"current_password": "admin-password"})


@pytest.mark.parametrize(
    ("service_function", "integration_function", "action"),
    [
        (users_service.reset_user_mfa, "reset_managed_user_mfa", _ACTION.ADMIN_MFA_RESET),
        (
            users_service.require_user_password_change,
            "require_managed_user_password_change",
            _ACTION.ADMIN_CREDENTIAL_CHANGE_REQUIRE,
        ),
    ],
)
class TestAdministratorCredentialActions:
    def test_commits_after_the_step_up_of_the_administrator(
        self, service_function, integration_function, action, mock_db
    ):
        store = MagicMock()
        request = _step_up_request()
        with patch(_ACCOUNT_SECURITY) as account_security:
            order = MagicMock()
            order.attach_mock(account_security.verify_step_up, "step_up")
            order.attach_mock(getattr(account_security, integration_function), "change")
            order.attach_mock(mock_db.commit, "commit")

            service_function(_U4, request, _U9, _SID_9, store, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "change", "commit"]
        account_security.verify_step_up.assert_called_once_with(request.step_up, _U9, _SID_9, action, store, mock_db)
        getattr(account_security, integration_function).assert_called_once_with(_U4, mock_db)

    def test_a_failed_step_up_changes_nothing(self, service_function, integration_function, action, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            _failing_step_up(account_security)
            service_function(_U4, _step_up_request(), _U9, _SID_9, MagicMock(), mock_db)

        getattr(account_security, integration_function).assert_not_called()
        mock_db.commit.assert_not_called()

    def test_an_administrator_cannot_target_their_own_account(
        self, service_function, integration_function, action, mock_db
    ):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            service_function(_U4, _step_up_request(), _U4, _SID_4, MagicMock(), mock_db)

        account_security.verify_step_up.assert_not_called()
        getattr(account_security, integration_function).assert_not_called()
        mock_db.commit.assert_not_called()

    def test_a_refusal_of_the_change_commits_nothing(self, service_function, integration_function, action, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.ConflictError):
            getattr(account_security, integration_function).side_effect = core_exceptions.ConflictError()
            service_function(_U4, _step_up_request(), _U9, _SID_9, MagicMock(), mock_db)

        mock_db.commit.assert_not_called()


class TestAdministratorUnlink:
    def test_commits_after_the_step_up_of_the_administrator(self, mock_db):
        store = MagicMock()
        step_up = auth_schema.StepUpVerification(current_password="admin-password")
        with patch(_ACCOUNT_SECURITY) as account_security:
            order = MagicMock()
            order.attach_mock(account_security.verify_step_up, "step_up")
            order.attach_mock(account_security.admin_delete_identity_provider_link, "unlink")
            order.attach_mock(mock_db.commit, "commit")

            users_service.unlink_identity_provider(_U4, _IDP_ID, _U8, _SID_8, step_up, store, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "unlink", "commit"]
        account_security.verify_step_up.assert_called_once_with(
            step_up, _U8, _SID_8, _ACTION.ADMIN_IDP_UNLINK, store, mock_db
        )
        account_security.admin_delete_identity_provider_link.assert_called_once_with(_U4, _IDP_ID, mock_db)

    def test_a_failed_step_up_changes_nothing(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            _failing_step_up(account_security)
            users_service.unlink_identity_provider(
                _U4, _IDP_ID, _U8, _SID_8, auth_schema.StepUpVerification(), MagicMock(), mock_db
            )

        account_security.admin_delete_identity_provider_link.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_an_administrator_cannot_unlink_their_own_identity_provider_here(self, mock_db):
        with patch(_ACCOUNT_SECURITY) as account_security, pytest.raises(core_exceptions.PermissionDeniedError):
            users_service.unlink_identity_provider(
                _U4, _IDP_ID, _U4, _SID_4, auth_schema.StepUpVerification(), MagicMock(), mock_db
            )

        account_security.verify_step_up.assert_not_called()
        account_security.admin_delete_identity_provider_link.assert_not_called()
        mock_db.commit.assert_not_called()
