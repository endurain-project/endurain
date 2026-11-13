"""Tests for users_profile.service module."""

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.service as profile_service

_SID_1 = uuid.UUID(int=101)
_MODULE = "modules.users.users_profile.service"
_USER_ID = uuid.UUID(int=1)


class TestEdits:
    @patch(f"{_MODULE}.users_integration")
    def test_profile_edit_stages_then_commits(self, mock_users, mock_db):
        profile = MagicMock()

        mock_users.edit_profile.return_value = MagicMock(version=4)

        with patch(f"{_MODULE}.get_profile", return_value=MagicMock(version=4)) as mock_get:
            updated = profile_service.edit_profile(_USER_ID, profile, mock_db, if_match="*")

        mock_users.edit_profile.assert_called_once_with(_USER_ID, profile, mock_db, if_match="*")
        mock_db.commit.assert_called_once()
        mock_get.assert_called_once_with(_USER_ID, mock_db)
        assert updated.version == 4

    @patch(f"{_MODULE}.users_privacy_settings_integration")
    def test_privacy_edit_stages_then_commits(self, mock_privacy, mock_db):
        settings = MagicMock()

        mock_privacy.edit_privacy_settings.return_value = MagicMock(version=6)

        updated = profile_service.edit_privacy_settings(_USER_ID, settings, mock_db, if_match="*")

        mock_privacy.edit_privacy_settings.assert_called_once_with(_USER_ID, settings, mock_db, if_match="*")
        mock_db.commit.assert_called_once()
        assert updated.version == 6

    @patch(f"{_MODULE}.users_integration")
    def test_a_failed_edit_does_not_commit(self, mock_users, mock_db):
        mock_users.edit_profile.side_effect = core_exceptions.ConflictError("taken")

        with pytest.raises(core_exceptions.ConflictError):
            profile_service.edit_profile(_USER_ID, MagicMock(), mock_db, if_match="*")

        mock_db.commit.assert_not_called()


class TestChangeEmail:
    @staticmethod
    def _change(identity, store, mock_db, *, state=None, **fields):
        import modules.users.users.schema as users_schema

        change = users_schema.EmailChange(
            email="New@Example.com",
            step_up={"current_password": "pw", "mfa_code": "123456"},
            **fields,
        )
        with (
            patch(
                "modules.auth.account_security.integration_service.verify_step_up",
                side_effect=lambda step_up, user_id, session_id, action, step_up_store, db: identity.verify_step_up(
                    step_up, user_id, session_id, action, step_up_store
                ),
            ),
            patch(
                "modules.auth.account_security.integration_service.delete_other_user_sessions",
                side_effect=lambda user_id, session_id, db: identity.delete_other_user_sessions(user_id, session_id),
            ),
            patch(f"{_MODULE}.get_profile"),
        ):
            profile_service.change_email(_USER_ID, change, _SID_1, store, state or MagicMock(), mock_db)

    @staticmethod
    def _users(mock_users, *, current="user1@example.com"):
        mock_users.require_user.return_value = MagicMock(email=current)
        return mock_users

    @patch(f"{_MODULE}.users_integration")
    def test_requests_the_change_only_after_the_step_up_and_commits_once(self, mock_users, mock_db):
        self._users(mock_users)
        identity = MagicMock()
        store = MagicMock()
        sign_up = MagicMock()
        sign_up.request_self_service_email_change.return_value = True
        order = MagicMock()
        order.attach_mock(identity.verify_step_up, "step_up")
        order.attach_mock(sign_up.request_self_service_email_change, "request")
        order.attach_mock(identity.delete_other_user_sessions, "revoke")
        order.attach_mock(mock_db.commit, "commit")

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            self._change(identity, store, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "request", "revoke", "commit"]
        identity.delete_other_user_sessions.assert_called_once_with(_USER_ID, _SID_1)
        verification = identity.verify_step_up.call_args.args
        assert (verification[0].current_password, verification[0].mfa_code) == ("pw", "123456")
        assert verification[1:] == (_USER_ID, _SID_1, identity_providers_constants.StepUpAction.EMAIL_CHANGE, store)
        sign_up.request_self_service_email_change.assert_called_once()
        assert sign_up.request_self_service_email_change.call_args.args[:3] == (
            _USER_ID,
            "new@example.com",
            "user1@example.com",
        )
        assert sign_up.request_self_service_email_change.call_args.args[4] is mock_db
        mock_users.stage_email_change.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_a_failed_step_up_changes_nothing(self, mock_users, mock_db):
        identity = MagicMock()
        identity.verify_step_up.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        with pytest.raises(core_exceptions.PermissionDeniedError):
            self._change(identity, MagicMock(), mock_db)

        mock_db.commit.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_other_sessions_end_when_the_request_omits_the_flag(self, mock_users, mock_db):
        self._users(mock_users)
        identity = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", MagicMock()):
            self._change(identity, MagicMock(), mock_db)

        identity.delete_other_user_sessions.assert_called_once_with(_USER_ID, _SID_1)

    @patch(f"{_MODULE}.users_integration")
    def test_other_sessions_stay_signed_in_when_the_client_sends_false(self, mock_users, mock_db):
        self._users(mock_users)
        identity = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", MagicMock()):
            self._change(identity, MagicMock(), mock_db, revoke_other_sessions=False)

        mock_db.commit.assert_called_once()
        identity.delete_other_user_sessions.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_resubmitting_the_current_address_cancels_a_pending_change_and_keeps_the_sessions(
        self, mock_users, mock_db
    ):
        self._users(mock_users, current="new@example.com")
        identity = MagicMock()
        sign_up = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            self._change(identity, MagicMock(), mock_db)

        sign_up.revoke_pending_tokens.assert_called_once_with(_USER_ID, mock_db)
        sign_up.request_self_service_email_change.assert_not_called()
        mock_db.commit.assert_called_once()
        identity.delete_other_user_sessions.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_an_instance_that_cannot_send_mail_still_changes_the_address(self, mock_users, mock_db):
        self._users(mock_users)
        sign_up = MagicMock()
        sign_up.request_self_service_email_change.return_value = False

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            self._change(MagicMock(), MagicMock(), mock_db)

        mock_users.stage_email_change.assert_called_once_with(_USER_ID, "new@example.com", mock_db)
        mock_db.commit.assert_called_once()


class TestResendAndCancelEmailChange:
    def test_resend_asks_for_the_resend_then_commits(self, mock_db):
        sign_up = MagicMock()
        state = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            profile_service.resend_email_change(_USER_ID, state, mock_db)

        sign_up.request_email_change_resend.assert_called_once_with(_USER_ID, state, mock_db)
        mock_db.commit.assert_called_once()

    def test_cancel_revokes_the_pending_tokens_then_commits(self, mock_db):
        sign_up = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            profile_service.cancel_email_change(_USER_ID, mock_db)

        sign_up.revoke_pending_tokens.assert_called_once_with(_USER_ID, mock_db)
        mock_db.commit.assert_called_once()


class TestStageExport:
    @patch(f"{_MODULE}.profile_export_service")
    @patch(f"{_MODULE}.profile_utils")
    @patch(f"{_MODULE}.users_integration")
    def test_server_managed_fields_never_reach_the_archive(self, mock_users, mock_utils, mock_export, mock_db):
        mock_utils.model_to_dict.return_value = {
            "name": "Test",
            "weight_units": "imperial",
            "password": "secret",
            "mfa_secret": "s",
            "access_type": "admin",
            "active": True,
            "mfa_enabled": True,
            "email_verified": True,
            "pending_admin_approval": False,
        }
        storage = MagicMock()
        mock_export.ExportService.return_value.build_export_archive.return_value = io.BytesIO(b"12345")
        storage.save_stream.return_value = 5

        size = profile_service.stage_export(_USER_ID, storage, mock_db)

        mock_export.ExportService.assert_called_once_with(_USER_ID, storage, mock_db)
        exported = mock_export.ExportService.return_value.build_export_archive.call_args.args[0]
        assert exported == {"name": "Test", "weight_units": "imperial"}
        assert size == 5
        area, key, archive = storage.save_stream.call_args.args
        assert (area, key) == ("profile_export_staging", f"{_USER_ID}.zip")
        assert archive.closed

    @patch(f"{_MODULE}.profile_export_service")
    @patch(f"{_MODULE}.profile_utils")
    @patch(f"{_MODULE}.users_integration")
    def test_a_failed_build_stages_nothing_and_is_a_domain_error(self, mock_users, mock_utils, mock_export, mock_db):
        mock_utils.model_to_dict.return_value = {}
        mock_export.ExportService.return_value.build_export_archive.side_effect = (
            profile_exceptions.DataCollectionError("boom")
        )

        storage = MagicMock()
        with pytest.raises(core_exceptions.DomainError):
            profile_service.stage_export(_USER_ID, storage, mock_db)

        storage.save_stream.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_unknown_user_is_not_found(self, mock_users, mock_db):
        mock_users.require_user.side_effect = core_exceptions.NotFoundError("User not found")

        with pytest.raises(core_exceptions.NotFoundError):
            profile_service.stage_export(_USER_ID, MagicMock(), mock_db)


class TestDeleteAccount:
    @patch(f"{_MODULE}.users_integration")
    def test_queues_the_deletion_only_after_the_step_up_passes(self, mock_users, mock_db):
        identity = MagicMock()
        step_up = MagicMock()
        store = MagicMock()
        state = MagicMock()
        storage = MagicMock()
        mail = MagicMock()
        order = MagicMock()
        order.attach_mock(identity.verify_step_up, "step_up")
        order.attach_mock(mock_users.request_user_deletion, "delete")

        with patch(
            "modules.auth.account_security.integration_service.verify_step_up",
            side_effect=lambda value, user_id, session_id, action, step_up_store, db: identity.verify_step_up(
                value, user_id, session_id, action, step_up_store
            ),
        ):
            result = profile_service.delete_account(_USER_ID, _SID_1, step_up, store, state, storage, mail, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "delete"]
        identity.verify_step_up.assert_called_once_with(
            step_up, _USER_ID, _SID_1, identity_providers_constants.StepUpAction.ACCOUNT_DELETE, store
        )
        mock_users.request_user_deletion.assert_called_once_with(_USER_ID, state, storage, mail, mock_db)
        assert result is mock_users.request_user_deletion.return_value

    @patch(f"{_MODULE}.users_integration")
    def test_a_failed_step_up_deletes_nothing(self, mock_users, mock_db):
        identity = MagicMock()
        identity.verify_step_up.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        with (
            pytest.raises(core_exceptions.PermissionDeniedError),
            patch(
                "modules.auth.account_security.integration_service.verify_step_up",
                side_effect=lambda step_up, user_id, session_id, action, step_up_store, db: identity.verify_step_up(
                    step_up, user_id, session_id, action, step_up_store
                ),
            ),
        ):
            profile_service.delete_account(
                _USER_ID, _SID_1, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_db
            )

        mock_users.request_user_deletion.assert_not_called()


class TestStateChangesAreLoggedAtInfo:
    @patch(f"{_MODULE}.users_integration")
    def test_a_profile_edit_logs_at_info(self, mock_users, mock_db, caplog):
        with (
            patch(f"{_MODULE}.get_profile", return_value=MagicMock(version=4)),
            caplog.at_level("DEBUG", logger=profile_service.logger.name),
        ):
            profile_service.edit_profile(_USER_ID, MagicMock(), mock_db, if_match="*")

        assert [record.levelname for record in caplog.records] == ["INFO"]

    @patch(f"{_MODULE}.users_privacy_settings_integration")
    def test_a_privacy_edit_logs_at_info(self, mock_privacy, mock_db, caplog):
        with caplog.at_level("DEBUG", logger=profile_service.logger.name):
            profile_service.edit_privacy_settings(_USER_ID, MagicMock(), mock_db, if_match="*")

        assert [record.levelname for record in caplog.records] == ["INFO"]
