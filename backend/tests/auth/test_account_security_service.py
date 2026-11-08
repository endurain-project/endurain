"""Tests for auth.account_security_service."""

from unittest.mock import MagicMock, patch

import pytest

import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.credentials.contracts as credentials_contracts

_PREFIX = "modules.auth.account_security.account_security_service."


@pytest.fixture(autouse=True)
def password_reset_tokens():
    """Replace the password-reset-token boundary."""
    with patch(_PREFIX + "password_reset_tokens_integration") as integration:
        yield integration


class TestChangeOwnPassword:
    """Tests for self-service password changes."""

    def test_the_current_password_is_refused_before_any_write_or_event(self, mock_db):
        """Reusing the current password writes no hash, ends no session and publishes no event."""
        prefix = "modules.auth.account_security.account_security_service."
        with (
            patch(prefix + "step_up_service.verify_step_up_credentials") as verify,
            patch(prefix + "credentials_integration.has_local_password", return_value=True),
            patch(
                prefix + "credentials_integration.ensure_password_differs_from_current",
                side_effect=credentials_contracts.PasswordUnchangedError(),
            ) as differs,
            patch(prefix + "credentials_integration.set_local_password_hash") as set_hash,
            patch(prefix + "sessions_integration.delete_sessions_by_user") as delete_sessions,
            patch(prefix + "account_security_event_publishers.publish_account_security_changed") as publish,
            pytest.raises(credentials_contracts.PasswordUnchangedError),
        ):
            account_security_service.stage_change_own_password(
                7,
                "same-pass",
                "same-pass",
                None,
                MagicMock(),
                mock_db,
                revoke_other_sessions=True,
                current_session_id="sid",
            )

        verify.assert_called_once()
        differs.assert_called_once_with(7, "same-pass", mock_db)
        set_hash.assert_not_called()
        delete_sessions.assert_not_called()
        publish.assert_not_called()

    @patch("modules.auth.account_security.account_security_service.logger")
    @patch("modules.auth.account_security.account_security_service.mfa_integration.clear_pending_mfa_for_user")
    @patch("modules.auth.account_security.account_security_service.step_up_service.verify_step_up_credentials")
    def test_verifies_updates_and_clears_pending_mfa(
        self,
        mock_verify,
        mock_clear_pending_mfa,
        mock_log,
        mock_db,
    ):
        """Self-service password change hashes in auth and owns all auth side effects."""
        step_up_store = MagicMock()

        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_user.username = "alice"
        mock_user.email = "alice@example.com"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12

        with (
            patch(
                "modules.auth.account_security.account_security_service.server_settings_integration.get_server_settings",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.has_local_password",
                return_value=True,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.ensure_password_differs_from_current"
            ),
            patch(
                "modules.auth.account_security.account_security_service.users_integration.require_user",
                return_value=mock_user,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.validate_and_hash_password_for_user",
                return_value="hashed-new-pass",
            ) as mock_hash_password,
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.set_local_password_hash"
            ) as mock_set_password,
        ):
            account_security_service.stage_change_own_password(
                user_id=7,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code="123456",
                step_up_store=step_up_store,
                db=mock_db,
                revoke_other_sessions=False,
                current_session_id="sid",
            )

        mock_verify.assert_called_once_with(
            7,
            "old-pass",
            "123456",
            step_up_store,
            mock_db,
            session_id="sid",
        )
        mock_hash_password.assert_called_once_with(
            mock_settings, "regular", "new-pass", mock_db, username="alice", email="alice@example.com"
        )
        mock_set_password.assert_called_once_with(7, "hashed-new-pass", mock_db, change_required=False)
        mock_clear_pending_mfa.assert_called_once_with(7)
        mock_db.commit.assert_not_called()
        assert len(mock_log.method_calls) == 1

    @patch("modules.auth.account_security.account_security_service.mfa_integration.clear_pending_mfa_for_user")
    @patch("modules.auth.account_security.account_security_service.step_up_service.verify_step_up_credentials")
    def test_admin_user_uses_admin_min_length(
        self,
        mock_verify,
        mock_clear_pending_mfa,
        mock_db,
    ):
        """Admin users get the admin minimum password length policy."""
        from modules.users.users.schema import UserAccessType

        step_up_store = MagicMock()

        mock_user = MagicMock()
        mock_user.access_type = UserAccessType.ADMIN
        mock_user.username = "alice"
        mock_user.email = "alice@example.com"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 16

        with (
            patch(
                "modules.auth.account_security.account_security_service.server_settings_integration.get_server_settings",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.has_local_password",
                return_value=True,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.ensure_password_differs_from_current"
            ),
            patch(
                "modules.auth.account_security.account_security_service.users_integration.require_user",
                return_value=mock_user,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.validate_and_hash_password_for_user",
                return_value="hashed-admin-pass",
            ) as mock_hash_password,
        ):
            account_security_service.stage_change_own_password(
                user_id=1,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code=None,
                step_up_store=step_up_store,
                db=mock_db,
                revoke_other_sessions=False,
                current_session_id="sid",
            )

        mock_hash_password.assert_called_once_with(
            mock_settings, "admin", "new-pass", mock_db, username="alice", email="alice@example.com"
        )

    @pytest.mark.parametrize("revoke", [True, False])
    def test_revokes_other_sessions_only_when_asked(self, revoke, mock_db):
        """Other sessions are deleted, keeping the current one, only when the caller asks."""
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_user.username = "alice"
        mock_user.email = "alice@example.com"
        prefix = "modules.auth.account_security.account_security_service."
        with (
            patch(prefix + "step_up_service.verify_step_up_credentials"),
            patch(prefix + "mfa_integration.clear_pending_mfa_for_user"),
            patch(prefix + "server_settings_integration.get_server_settings"),
            patch(prefix + "credentials_integration.has_local_password", return_value=True),
            patch(prefix + "credentials_integration.ensure_password_differs_from_current"),
            patch(prefix + "users_integration.require_user", return_value=mock_user),
            patch(prefix + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(prefix + "credentials_integration.set_local_password_hash"),
            patch(prefix + "sessions_integration.delete_sessions_by_user") as mock_delete_sessions,
        ):
            account_security_service.stage_change_own_password(
                user_id=7,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code=None,
                step_up_store=MagicMock(),
                db=mock_db,
                revoke_other_sessions=revoke,
                current_session_id="session-1",
            )

        if revoke:
            mock_delete_sessions.assert_called_once_with(7, mock_db, exclude_session_id="session-1")
        else:
            mock_delete_sessions.assert_not_called()


class TestChangeManagedUserPassword:
    """Tests for managed user password changes."""

    def test_voids_the_users_unused_reset_tokens(self, mock_db, password_reset_tokens):
        """A reset link mailed before the administrator set a password stops working."""
        mock_user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
        with (
            patch(_PREFIX + "server_settings_integration.get_server_settings"),
            patch(_PREFIX + "users_integration.require_user", return_value=mock_user),
            patch(_PREFIX + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(_PREFIX + "credentials_integration.set_local_password_hash"),
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user"),
            patch(_PREFIX + "mfa_integration.clear_pending_mfa_for_user"),
        ):
            account_security_service.change_managed_user_password(42, "new-pass", mock_db)

        password_reset_tokens.revoke_unused_tokens.assert_called_once_with(42, mock_db)

    @patch("modules.auth.account_security.account_security_service.mfa_integration.clear_pending_mfa_for_user")
    @patch("modules.auth.account_security.account_security_service.sessions_integration.delete_sessions_by_user")
    def test_updates_password_revokes_sessions_and_clears_pending_mfa(
        self,
        mock_delete_sessions,
        mock_clear_pending_mfa,
        mock_db,
    ):
        """Managed password change hashes in auth and owns all auth side effects."""

        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_user.username = "alice"
        mock_user.email = "alice@example.com"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12

        with (
            patch(
                "modules.auth.account_security.account_security_service.server_settings_integration.get_server_settings",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.has_local_password",
                return_value=True,
            ),
            patch(
                "modules.auth.account_security.account_security_service.users_integration.require_user",
                return_value=mock_user,
            ),
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.validate_and_hash_password_for_user",
                return_value="hashed-managed-pass",
            ) as mock_hash_password,
            patch(
                "modules.auth.account_security.account_security_service.credentials_integration.set_local_password_hash"
            ) as mock_set_password,
        ):
            account_security_service.change_managed_user_password(
                user_id=42,
                new_password="new-pass",
                db=mock_db,
            )

        mock_hash_password.assert_called_once_with(
            mock_settings, "regular", "new-pass", mock_db, username="alice", email="alice@example.com"
        )
        # An administrator knows this password, so the user must change it at the next sign-in.
        mock_set_password.assert_called_once_with(42, "hashed-managed-pass", mock_db, change_required=True)

        mock_delete_sessions.assert_called_once_with(42, mock_db)
        mock_clear_pending_mfa.assert_called_once_with(42)


class TestChangeOwnPasswordResetTokens:
    """A password change voids the reset links mailed before it."""

    def test_voids_the_users_unused_reset_tokens(self, mock_db, password_reset_tokens):
        mock_user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
        with (
            patch(_PREFIX + "step_up_service.verify_step_up_credentials"),
            patch(_PREFIX + "mfa_integration.clear_pending_mfa_for_user"),
            patch(_PREFIX + "server_settings_integration.get_server_settings"),
            patch(_PREFIX + "credentials_integration.has_local_password", return_value=True),
            patch(_PREFIX + "credentials_integration.ensure_password_differs_from_current"),
            patch(_PREFIX + "users_integration.require_user", return_value=mock_user),
            patch(_PREFIX + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(_PREFIX + "credentials_integration.set_local_password_hash"),
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user"),
        ):
            account_security_service.stage_change_own_password(
                7,
                "old-pass",
                "new-pass",
                None,
                MagicMock(),
                mock_db,
                revoke_other_sessions=False,
                current_session_id="sid",
            )

        password_reset_tokens.revoke_unused_tokens.assert_called_once_with(7, mock_db)


class TestDeleteOtherUserSessions:
    """Tests for self-service 'revoke other sessions'."""

    @patch("modules.auth.account_security.account_security_service.logger")
    @patch("modules.auth.account_security.account_security_service.sessions_integration.delete_sessions_by_user")
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
        assert len(mock_log.method_calls) == 1


class TestDeleteUserSessionLogging:
    """Deleting a session logs a fingerprint of its id, never the id itself."""

    @patch("modules.auth.account_security.account_security_service.sessions_integration.delete_session")
    def test_the_raw_session_id_is_not_logged(self, mock_delete, mock_db, caplog):
        import logging

        import core.hashing as core_hashing

        session_id = "9f2c1d7e-session-handle-0001"

        with caplog.at_level(logging.DEBUG):
            account_security_service.delete_user_session(session_id, 42, mock_db)

        assert caplog.records
        for record in caplog.records:
            assert session_id not in record.getMessage()
            assert session_id not in str(record.__dict__)
        assert any(core_hashing.log_fingerprint(session_id) in str(record.__dict__) for record in caplog.records)
