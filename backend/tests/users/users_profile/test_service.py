"""Tests for users_profile.service module."""

import io
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.users.users_profile.exceptions as profile_exceptions
import modules.users.users_profile.service as profile_service

_MODULE = "modules.users.users_profile.service"


class TestEdits:
    @patch(f"{_MODULE}.users_integration")
    def test_profile_edit_stages_then_commits(self, mock_users, mock_db):
        profile = MagicMock()

        mock_users.edit_profile.return_value = MagicMock(version=4)

        with patch(f"{_MODULE}.get_profile", return_value=MagicMock(version=4)) as mock_get:
            updated = profile_service.edit_profile(1, profile, mock_db, if_match="*")

        mock_users.edit_profile.assert_called_once_with(1, profile, mock_db, if_match="*")
        mock_db.commit.assert_called_once()
        mock_get.assert_called_once_with(1, mock_db)
        assert updated.version == 4

    @patch(f"{_MODULE}.users_privacy_settings_integration")
    def test_privacy_edit_stages_then_commits(self, mock_privacy, mock_db):
        settings = MagicMock()

        mock_privacy.edit_privacy_settings.return_value = MagicMock(version=6)

        updated = profile_service.edit_privacy_settings(1, settings, mock_db, if_match="*")

        mock_privacy.edit_privacy_settings.assert_called_once_with(1, settings, mock_db, if_match="*")
        mock_db.commit.assert_called_once()
        assert updated.version == 6

    @patch(f"{_MODULE}.users_integration")
    def test_a_failed_edit_does_not_commit(self, mock_users, mock_db):
        mock_users.edit_profile.side_effect = core_exceptions.ConflictError("taken")

        with pytest.raises(core_exceptions.ConflictError):
            profile_service.edit_profile(1, MagicMock(), mock_db, if_match="*")

        mock_db.commit.assert_not_called()


class TestChangeEmail:
    @staticmethod
    def _change(identity, store, mock_db, *, revoke_other_sessions=True):
        import modules.users.users.schema as users_schema

        change = users_schema.EmailChange(
            email="New@Example.com",
            current_password="pw",
            mfa_code="123456",
            revoke_other_sessions=revoke_other_sessions,
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
            profile_service.change_email(1, change, "sid-1", store, mock_db)

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
        sign_up.request_email_change.return_value = True
        order = MagicMock()
        order.attach_mock(identity.verify_step_up, "step_up")
        order.attach_mock(mock_users.require_email_available, "available")
        order.attach_mock(sign_up.request_email_change, "request")
        order.attach_mock(identity.delete_other_user_sessions, "revoke")
        order.attach_mock(mock_db.commit, "commit")

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            self._change(identity, store, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "available", "request", "revoke", "commit"]
        identity.delete_other_user_sessions.assert_called_once_with(1, "sid-1")
        verification = identity.verify_step_up.call_args.args
        assert (verification[0].current_password, verification[0].mfa_code) == ("pw", "123456")
        assert verification[1:] == (1, "sid-1", identity_providers_constants.StepUpAction.EMAIL_CHANGE, store)
        mock_users.require_email_available.assert_called_once_with(1, "new@example.com", mock_db)
        sign_up.request_email_change.assert_called_once_with(1, "new@example.com", "user1@example.com", mock_db)
        mock_users.stage_email_change.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_a_failed_step_up_changes_nothing(self, mock_users, mock_db):
        identity = MagicMock()
        identity.verify_step_up.side_effect = core_exceptions.PermissionDeniedError("wrong password")

        with pytest.raises(core_exceptions.PermissionDeniedError):
            self._change(identity, MagicMock(), mock_db)

        mock_users.require_email_available.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_a_taken_address_rolls_back_and_stages_nothing(self, mock_users, mock_db):
        self._users(mock_users)
        mock_users.require_email_available.side_effect = core_exceptions.ConflictError("taken")
        sign_up = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up), pytest.raises(core_exceptions.ConflictError):
            self._change(MagicMock(), MagicMock(), mock_db)

        sign_up.request_email_change.assert_not_called()
        mock_db.rollback.assert_called_once()
        mock_db.commit.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_other_sessions_stay_signed_in_unless_asked(self, mock_users, mock_db):
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

        sign_up.revoke_pending_tokens.assert_called_once_with(1, mock_db)
        sign_up.request_email_change.assert_not_called()
        mock_db.commit.assert_called_once()
        identity.delete_other_user_sessions.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_an_instance_that_cannot_send_mail_still_changes_the_address(self, mock_users, mock_db):
        self._users(mock_users)
        sign_up = MagicMock()
        sign_up.request_email_change.return_value = False

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            self._change(MagicMock(), MagicMock(), mock_db)

        mock_users.stage_email_change.assert_called_once_with(1, "new@example.com", mock_db)
        mock_db.commit.assert_called_once()


class TestResendAndCancelEmailChange:
    def test_resend_asks_for_the_resend_then_commits(self, mock_db):
        sign_up = MagicMock()
        state = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            profile_service.resend_email_change(1, state, mock_db)

        sign_up.request_email_change_resend.assert_called_once_with(1, state, mock_db)
        mock_db.commit.assert_called_once()

    def test_cancel_revokes_the_pending_tokens_then_commits(self, mock_db):
        sign_up = MagicMock()

        with patch(f"{_MODULE}.sign_up_tokens_integration", sign_up):
            profile_service.cancel_email_change(1, mock_db)

        sign_up.revoke_pending_tokens.assert_called_once_with(1, mock_db)
        mock_db.commit.assert_called_once()


class TestStageExport:
    @patch(f"{_MODULE}.profile_export_service")
    @patch(f"{_MODULE}.profile_utils")
    @patch(f"{_MODULE}.users_integration")
    def test_server_managed_fields_never_reach_the_archive(self, mock_users, mock_utils, mock_export, mock_db):
        mock_utils.sqlalchemy_obj_to_dict.return_value = {
            "name": "Test",
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

        size = profile_service.stage_export(1, storage, mock_db)

        mock_export.ExportService.assert_called_once_with(1, storage, mock_db)
        exported = mock_export.ExportService.return_value.build_export_archive.call_args.args[0]
        assert exported == {"name": "Test"}
        assert size == 5
        area, key, archive = storage.save_stream.call_args.args
        assert (area, key) == ("profile_export_staging", "1.zip")
        assert archive.closed

    @patch(f"{_MODULE}.profile_export_service")
    @patch(f"{_MODULE}.profile_utils")
    @patch(f"{_MODULE}.users_integration")
    def test_a_failed_build_stages_nothing_and_is_a_domain_error(self, mock_users, mock_utils, mock_export, mock_db):
        mock_utils.sqlalchemy_obj_to_dict.return_value = {}
        mock_export.ExportService.return_value.build_export_archive.side_effect = (
            profile_exceptions.DataCollectionError("boom")
        )

        storage = MagicMock()
        with pytest.raises(core_exceptions.DomainError):
            profile_service.stage_export(1, storage, mock_db)

        storage.save_stream.assert_not_called()

    @patch(f"{_MODULE}.users_integration")
    def test_unknown_user_is_not_found(self, mock_users, mock_db):
        mock_users.require_user.side_effect = core_exceptions.NotFoundError("User not found")

        with pytest.raises(core_exceptions.NotFoundError):
            profile_service.stage_export(1, MagicMock(), mock_db)


class TestDeleteAccount:
    @patch(f"{_MODULE}.users_integration")
    def test_queues_the_deletion_only_after_the_step_up_passes(self, mock_users, mock_db):
        identity = MagicMock()
        step_up = MagicMock()
        store = MagicMock()
        state = MagicMock()
        storage = MagicMock()
        order = MagicMock()
        order.attach_mock(identity.verify_step_up, "step_up")
        order.attach_mock(mock_users.request_user_deletion, "delete")

        with patch(
            "modules.auth.account_security.integration_service.verify_step_up",
            side_effect=lambda value, user_id, session_id, action, step_up_store, db: identity.verify_step_up(
                value, user_id, session_id, action, step_up_store
            ),
        ):
            result = profile_service.delete_account(1, "sid-1", step_up, store, state, storage, mock_db)

        assert [call[0] for call in order.mock_calls] == ["step_up", "delete"]
        identity.verify_step_up.assert_called_once_with(
            step_up, 1, "sid-1", identity_providers_constants.StepUpAction.ACCOUNT_DELETE, store
        )
        mock_users.request_user_deletion.assert_called_once_with(1, state, storage, mock_db)
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
            profile_service.delete_account(1, "sid-1", MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_db)

        mock_users.request_user_deletion.assert_not_called()


class TestStateChangesAreLoggedAtInfo:
    @patch(f"{_MODULE}.users_integration")
    def test_a_profile_edit_logs_at_info(self, mock_users, mock_db, caplog):
        with (
            patch(f"{_MODULE}.get_profile", return_value=MagicMock(version=4)),
            caplog.at_level("DEBUG", logger=profile_service.logger.name),
        ):
            profile_service.edit_profile(1, MagicMock(), mock_db, if_match="*")

        assert [record.levelname for record in caplog.records] == ["INFO"]

    @patch(f"{_MODULE}.users_privacy_settings_integration")
    def test_a_privacy_edit_logs_at_info(self, mock_privacy, mock_db, caplog):
        with caplog.at_level("DEBUG", logger=profile_service.logger.name):
            profile_service.edit_privacy_settings(1, MagicMock(), mock_db, if_match="*")

        assert [record.levelname for record in caplog.records] == ["INFO"]

    def test_starting_an_identity_provider_link_logs_at_info(self, mock_db, caplog):
        with patch(f"{_MODULE}.account_security_integration") as account_security:
            account_security.stage_browser_idp_link.return_value = MagicMock(browser_binding="binding")
            account_security.browser_flow_authorization_url.return_value = "https://idp.example.com/auth"
            with caplog.at_level("DEBUG", logger=profile_service.logger.name):
                profile_service.start_identity_provider_link("token", 2, "/settings", "10.0.0.1", mock_db)

        assert [record.levelname for record in caplog.records] == ["INFO"]
