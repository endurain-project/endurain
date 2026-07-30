"""Tests for auth.account_security_service."""

from unittest.mock import MagicMock, patch

import modules.auth._internal.services.account_security_service as account_security_service


class TestChangeOwnPassword:
    """Tests for self-service password changes."""

    @patch("modules.auth._internal.services.account_security_service.core_logger.print_to_log")
    @patch("modules.auth._internal.services.account_security_service.auth_security_stores.clear_pending_mfa_for_user")
    @patch("modules.auth._internal.services.account_security_service.step_up_service.verify_step_up_credentials")
    def test_verifies_updates_and_clears_pending_mfa(
        self,
        mock_verify,
        mock_clear_pending_mfa,
        mock_log,
        mock_db,
    ):
        """Self-service password change hashes in auth and owns all auth side effects."""
        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "hashed-new-pass"
        step_up_store = MagicMock()

        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12
        mock_settings.password_type = "strict"

        with (
            patch(
                "modules.auth._internal.services.account_security_service.server_settings_utils.get_server_settings_or_404",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth._internal.services.account_security_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
        ):
            account_security_service.change_own_password(
                user_id=7,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code="123456",
                identity_service=identity_service,
                step_up_store=step_up_store,
                db=mock_db,
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            "123456",
            identity_service,
            step_up_store,
            mock_db,
        )
        identity_service.validate_and_hash_password.assert_called_once_with(
            "new-pass",
            8,
            "strict",
        )
        identity_service.set_local_password_hash.assert_called_once_with(
            7,
            "hashed-new-pass",
        )
        mock_clear_pending_mfa.assert_called_once_with(7)
        mock_log.assert_called_once()

    @patch("modules.auth._internal.services.account_security_service.core_logger.print_to_log")
    @patch("modules.auth._internal.services.account_security_service.auth_security_stores.clear_pending_mfa_for_user")
    @patch("modules.auth._internal.services.account_security_service.step_up_service.verify_step_up_credentials")
    def test_admin_user_uses_admin_min_length(
        self,
        mock_verify,
        mock_clear_pending_mfa,
        mock_log,
        mock_db,
    ):
        """Admin users get the admin minimum password length policy."""
        from modules.users.users.schema import UserAccessType

        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "hashed-admin-pass"
        step_up_store = MagicMock()

        mock_user = MagicMock()
        mock_user.access_type = UserAccessType.ADMIN
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 16
        mock_settings.password_type = "strict"

        with (
            patch(
                "modules.auth._internal.services.account_security_service.server_settings_utils.get_server_settings_or_404",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth._internal.services.account_security_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
        ):
            account_security_service.change_own_password(
                user_id=1,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code=None,
                identity_service=identity_service,
                step_up_store=step_up_store,
                db=mock_db,
            )

        identity_service.validate_and_hash_password.assert_called_once_with(
            "new-pass",
            16,
            "strict",
        )


class TestChangeManagedUserPassword:
    """Tests for managed user password changes."""

    @patch("modules.auth._internal.services.account_security_service.auth_security_stores.clear_pending_mfa_for_user")
    @patch("modules.auth._internal.services.account_security_service.auth_sessions_crud.delete_sessions_by_user")
    def test_updates_password_revokes_sessions_and_clears_pending_mfa(
        self,
        mock_delete_sessions,
        mock_clear_pending_mfa,
        mock_db,
    ):
        """Managed password change hashes in auth and owns all auth side effects."""
        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "hashed-managed-pass"

        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12
        mock_settings.password_type = "strict"

        with (
            patch(
                "modules.auth._internal.services.account_security_service.server_settings_utils.get_server_settings_or_404",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth._internal.services.account_security_service.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
        ):
            account_security_service.change_managed_user_password(
                user_id=42,
                new_password="new-pass",
                identity_service=identity_service,
                db=mock_db,
            )

        identity_service.validate_and_hash_password.assert_called_once_with(
            "new-pass",
            8,
            "strict",
        )
        identity_service.set_local_password_hash.assert_called_once_with(
            42,
            "hashed-managed-pass",
        )
        mock_delete_sessions.assert_called_once_with(42, mock_db)
        mock_clear_pending_mfa.assert_called_once_with(42)


class TestDeleteOtherUserSessions:
    """Tests for self-service 'revoke other sessions'."""

    @patch("modules.auth._internal.services.account_security_service.core_logger.print_to_log")
    @patch("modules.auth._internal.services.account_security_service.auth_sessions_crud.delete_sessions_by_user")
    def test_revokes_all_sessions_except_current(
        self,
        mock_delete_sessions,
        mock_log,
        mock_db,
    ):
        """Deletes every session except the caller's current one and returns the count."""
        mock_delete_sessions.return_value = 3

        revoked = account_security_service.delete_other_user_sessions(
            token_user_id=7,
            current_session_id="session-1",
            db=mock_db,
        )

        assert revoked == 3
        mock_delete_sessions.assert_called_once_with(
            7,
            mock_db,
            exclude_session_id="session-1",
        )
        mock_log.assert_called_once()
