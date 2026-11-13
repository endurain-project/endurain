"""Tests for auth.account_security_service."""

import uuid
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

import modules.auth.account_security.account_security_service as account_security_service
import modules.auth.credentials.contracts as credentials_contracts

_SID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
_SID_2 = uuid.UUID("00000000-0000-4000-8000-0000000000a2")

USER_ID = uuid.UUID(int=7)
OTHER_USER_ID = uuid.UUID(int=42)
_PREFIX = "modules.auth.account_security.account_security_service."


@pytest.fixture(autouse=True)
def api_keys():
    """Replace the API-key boundary."""
    with patch(_PREFIX + "api_keys_integration") as integration:
        yield integration


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
                prefix + "server_settings_integration.get_server_settings",
                return_value=MagicMock(password_breach_check_enabled=False),
            ),
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
                USER_ID,
                "same-pass",
                "same-pass",
                None,
                MagicMock(),
                mock_db,
                revoke_other_sessions=True,
                current_session_id=_SID,
            )

        verify.assert_called_once()
        differs.assert_called_once_with(USER_ID, "same-pass", mock_db)
        set_hash.assert_not_called()
        delete_sessions.assert_not_called()
        publish.assert_not_called()

    @patch("modules.auth.account_security.account_security_service.logger")
    @patch("modules.auth.account_security.account_security_service.step_up_service.verify_step_up_credentials")
    def test_verifies_and_updates(
        self,
        mock_verify,
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
                user_id=USER_ID,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code="123456",
                step_up_store=step_up_store,
                db=mock_db,
                revoke_other_sessions=False,
                current_session_id=_SID,
            )

        mock_verify.assert_called_once_with(
            USER_ID,
            "old-pass",
            "123456",
            step_up_store,
            mock_db,
            session_id=_SID,
        )
        mock_hash_password.assert_called_once_with(
            mock_settings, "regular", "new-pass", mock_db, username="alice", email="alice@example.com"
        )
        mock_set_password.assert_called_once_with(USER_ID, "hashed-new-pass", mock_db, change_required=False)
        mock_db.commit.assert_not_called()
        assert len(mock_log.method_calls) == 1

    @patch("modules.auth.account_security.account_security_service.step_up_service.verify_step_up_credentials")
    def test_admin_user_uses_admin_min_length(
        self,
        mock_verify,
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
                user_id=USER_ID,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code=None,
                step_up_store=step_up_store,
                db=mock_db,
                revoke_other_sessions=False,
                current_session_id=_SID,
            )

        mock_hash_password.assert_called_once_with(
            mock_settings, "admin", "new-pass", mock_db, username="alice", email="alice@example.com"
        )

    def test_keeps_the_users_api_keys(self, mock_db, api_keys):
        """The user is signed in and manages their keys on the keys page; a change of password keeps them."""
        mock_user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
        prefix = "modules.auth.account_security.account_security_service."
        with (
            patch(prefix + "step_up_service.verify_step_up_credentials"),
            patch(prefix + "server_settings_integration.get_server_settings"),
            patch(prefix + "credentials_integration.has_local_password", return_value=True),
            patch(prefix + "credentials_integration.ensure_password_differs_from_current"),
            patch(prefix + "users_integration.require_user", return_value=mock_user),
            patch(prefix + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(prefix + "credentials_integration.set_local_password_hash"),
            patch(prefix + "sessions_integration.delete_sessions_by_user"),
        ):
            account_security_service.stage_change_own_password(
                user_id=USER_ID,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code=None,
                step_up_store=MagicMock(),
                db=mock_db,
                revoke_other_sessions=True,
                current_session_id=_SID_2,
            )

        api_keys.revoke_user_api_keys.assert_not_called()

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
            patch(prefix + "server_settings_integration.get_server_settings"),
            patch(prefix + "credentials_integration.has_local_password", return_value=True),
            patch(prefix + "credentials_integration.ensure_password_differs_from_current"),
            patch(prefix + "users_integration.require_user", return_value=mock_user),
            patch(prefix + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(prefix + "credentials_integration.set_local_password_hash"),
            patch(prefix + "sessions_integration.delete_sessions_by_user") as mock_delete_sessions,
        ):
            account_security_service.stage_change_own_password(
                user_id=USER_ID,
                current_password="old-pass",
                new_password="new-pass",
                mfa_code=None,
                step_up_store=MagicMock(),
                db=mock_db,
                revoke_other_sessions=revoke,
                current_session_id=_SID_2,
            )

        if revoke:
            mock_delete_sessions.assert_called_once_with(USER_ID, mock_db, exclude_session_id=_SID_2)
        else:
            mock_delete_sessions.assert_not_called()


class TestChangeManagedUserPassword:
    """Tests for managed user password changes."""

    def test_revokes_the_users_api_keys(self, mock_db, api_keys):
        """The administrator knows the password, and whoever held the old one may hold a key."""
        mock_user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
        with (
            patch(_PREFIX + "server_settings_integration.get_server_settings"),
            patch(_PREFIX + "users_integration.require_user", return_value=mock_user),
            patch(_PREFIX + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(_PREFIX + "credentials_integration.set_local_password_hash"),
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user"),
        ):
            account_security_service.change_managed_user_password(OTHER_USER_ID, "new-pass", mock_db)

        api_keys.revoke_user_api_keys.assert_called_once_with(OTHER_USER_ID, mock_db)

    def test_voids_the_users_unused_reset_tokens(self, mock_db, password_reset_tokens):
        """A reset link mailed before the administrator set a password stops working."""
        mock_user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
        with (
            patch(_PREFIX + "server_settings_integration.get_server_settings"),
            patch(_PREFIX + "users_integration.require_user", return_value=mock_user),
            patch(_PREFIX + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(_PREFIX + "credentials_integration.set_local_password_hash"),
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user"),
        ):
            account_security_service.change_managed_user_password(OTHER_USER_ID, "new-pass", mock_db)

        password_reset_tokens.revoke_unused_tokens.assert_called_once_with(OTHER_USER_ID, mock_db)

    @patch("modules.auth.account_security.account_security_service.sessions_integration.delete_sessions_by_user")
    def test_updates_password_and_revokes_sessions(
        self,
        mock_delete_sessions,
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
                user_id=OTHER_USER_ID,
                new_password="new-pass",
                db=mock_db,
            )

        mock_hash_password.assert_called_once_with(
            mock_settings, "regular", "new-pass", mock_db, username="alice", email="alice@example.com"
        )
        # An administrator knows this password, so the user must change it at the next sign-in.
        mock_set_password.assert_called_once_with(OTHER_USER_ID, "hashed-managed-pass", mock_db, change_required=True)

        mock_delete_sessions.assert_called_once_with(OTHER_USER_ID, mock_db)


class TestChangeOwnPasswordResetTokens:
    """A password change voids the reset links mailed before it."""

    def test_voids_the_users_unused_reset_tokens(self, mock_db, password_reset_tokens):
        mock_user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
        with (
            patch(_PREFIX + "step_up_service.verify_step_up_credentials"),
            patch(_PREFIX + "server_settings_integration.get_server_settings"),
            patch(_PREFIX + "credentials_integration.has_local_password", return_value=True),
            patch(_PREFIX + "credentials_integration.ensure_password_differs_from_current"),
            patch(_PREFIX + "users_integration.require_user", return_value=mock_user),
            patch(_PREFIX + "credentials_integration.validate_and_hash_password_for_user", return_value="hashed"),
            patch(_PREFIX + "credentials_integration.set_local_password_hash"),
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user"),
        ):
            account_security_service.stage_change_own_password(
                USER_ID,
                "old-pass",
                "new-pass",
                None,
                MagicMock(),
                mock_db,
                revoke_other_sessions=False,
                current_session_id=_SID,
            )

        password_reset_tokens.revoke_unused_tokens.assert_called_once_with(USER_ID, mock_db)


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
            token_user_id=USER_ID,
            current_session_id=_SID_2,
            db=mock_db,
        )

        assert revoked == 3
        mock_delete_sessions.assert_called_once_with(
            USER_ID,
            mock_db,
            exclude_session_id=_SID_2,
        )
        assert len(mock_log.method_calls) == 1


class TestDeleteUserSessionLogging:
    """Deleting a session logs a fingerprint of its id, never the id itself."""

    @patch("modules.auth.account_security.account_security_service.sessions_integration.delete_session")
    def test_the_raw_session_id_is_not_logged(self, mock_delete, mock_db, caplog):
        import logging

        import core.hashing as core_hashing

        session_id = uuid.UUID("9f2c1d7e-5a3b-4c1d-8e2f-000000000001")

        with caplog.at_level(logging.DEBUG):
            account_security_service.delete_user_session(session_id, OTHER_USER_ID, mock_db)

        assert caplog.records
        for record in caplog.records:
            assert str(session_id) not in record.getMessage()
            assert str(session_id) not in str(record.__dict__)
        assert any(core_hashing.log_fingerprint(str(session_id)) in str(record.__dict__) for record in caplog.records)


class TestSecurityGenerationBump:
    """Each security change advances the account's security generation in its own transaction."""

    @pytest.fixture
    def generation(self):
        with patch(_PREFIX + "security_generation_integration") as integration:
            yield integration

    @staticmethod
    def _enter(stack, *names):
        """Enter the patches of the password write's collaborators that ``names`` select."""
        user = MagicMock(access_type="regular", username="alice", email="alice@example.com")
        patches = {
            "settings": patch(_PREFIX + "server_settings_integration.get_server_settings"),
            "differs": patch(_PREFIX + "credentials_integration.ensure_password_differs_from_current"),
            "user": patch(_PREFIX + "users_integration.require_user", return_value=user),
            "hash": patch(_PREFIX + "credentials_integration.validate_and_hash_password_for_user", return_value="h"),
            "set_hash": patch(_PREFIX + "credentials_integration.set_local_password_hash"),
            "sessions": patch(_PREFIX + "sessions_integration.delete_sessions_by_user", return_value=0),
            "lockout": patch(_PREFIX + "authentication_integration.clear_account_login_lockout"),
            "audit": patch(_PREFIX + "_stage_credential_changed"),
            "has_password": patch(_PREFIX + "credentials_integration.has_local_password", return_value=True),
            "step_up": patch(_PREFIX + "step_up_service.verify_step_up_credentials"),
        }
        for name in names:
            stack.enter_context(patches[name])

    def test_an_own_password_change_bumps(self, mock_db, generation):
        with ExitStack() as stack:
            self._enter(
                stack,
                "step_up",
                "settings",
                "has_password",
                "differs",
                "user",
                "hash",
                "set_hash",
                "sessions",
                "lockout",
                "audit",
            )
            account_security_service.stage_change_own_password(
                USER_ID, "old", "new", None, MagicMock(), mock_db, revoke_other_sessions=False, current_session_id=_SID
            )

        generation.stage_bump.assert_called_once_with(USER_ID, mock_db)

    def test_the_forced_password_change_bumps(self, mock_db, generation):
        with ExitStack() as stack:
            self._enter(stack, "settings", "differs", "user", "hash", "set_hash", "audit")
            account_security_service.stage_required_password_change(USER_ID, "new", mock_db)

        generation.stage_bump.assert_called_once_with(USER_ID, mock_db)

    def test_a_refused_own_password_change_does_not_bump(self, mock_db, generation):
        with (
            patch(_PREFIX + "credentials_integration.has_local_password", return_value=False),
            pytest.raises(Exception, match="identity provider"),
        ):
            account_security_service.stage_change_own_password(
                USER_ID, "old", "new", None, MagicMock(), mock_db, revoke_other_sessions=False, current_session_id=_SID
            )

        generation.stage_bump.assert_not_called()

    def test_an_administrator_setting_a_password_bumps(self, mock_db, generation):
        with ExitStack() as stack:
            self._enter(stack, "settings", "user", "hash", "set_hash", "sessions", "lockout", "audit")
            account_security_service.change_managed_user_password(OTHER_USER_ID, "new", mock_db)

        generation.stage_bump.assert_called_once_with(OTHER_USER_ID, mock_db)

    def test_requiring_a_password_change_bumps(self, mock_db, generation):
        with (
            patch(_PREFIX + "users_integration.require_user"),
            patch(_PREFIX + "credentials_integration.require_password_change"),
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user", return_value=0),
            patch(_PREFIX + "_stage_credential_changed"),
        ):
            account_security_service.require_managed_user_password_change(OTHER_USER_ID, mock_db)

        generation.stage_bump.assert_called_once_with(OTHER_USER_ID, mock_db)

    def test_an_own_password_change_bumps_before_the_password_is_written(self, mock_db, generation):
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        with ExitStack() as stack:
            self._enter(stack, "step_up", "settings", "has_password", "differs", "user", "hash", "lockout", "audit")
            order.attach_mock(
                stack.enter_context(patch(_PREFIX + "credentials_integration.set_local_password_hash")), "set_password"
            )
            order.attach_mock(
                stack.enter_context(patch(_PREFIX + "sessions_integration.delete_sessions_by_user", return_value=0)),
                "delete_sessions",
            )
            account_security_service.stage_change_own_password(
                USER_ID, "old", "new", None, MagicMock(), mock_db, revoke_other_sessions=True, current_session_id=_SID
            )

        names = [call[0] for call in order.mock_calls]
        assert names.index("bump") < names.index("set_password")
        assert names.index("bump") < names.index("delete_sessions")

    def test_the_forced_password_change_bumps_before_the_password_is_written(self, mock_db, generation):
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        with ExitStack() as stack:
            self._enter(stack, "settings", "differs", "user", "hash", "audit")
            order.attach_mock(
                stack.enter_context(patch(_PREFIX + "credentials_integration.set_local_password_hash")), "set_password"
            )
            account_security_service.stage_required_password_change(USER_ID, "new", mock_db)

        assert [call[0] for call in order.mock_calls][:2] == ["bump", "set_password"]

    def test_an_administrator_setting_a_password_bumps_before_any_other_write(self, mock_db, generation):
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        with ExitStack() as stack:
            self._enter(stack, "settings", "user", "hash", "lockout", "audit")
            order.attach_mock(
                stack.enter_context(patch(_PREFIX + "credentials_integration.set_local_password_hash")), "set_password"
            )
            order.attach_mock(
                stack.enter_context(patch(_PREFIX + "password_reset_tokens_integration.revoke_unused_tokens")),
                "void_tokens",
            )
            order.attach_mock(
                stack.enter_context(patch(_PREFIX + "sessions_integration.delete_sessions_by_user", return_value=0)),
                "delete_sessions",
            )
            account_security_service.change_managed_user_password(OTHER_USER_ID, "new", mock_db)

        assert [call[0] for call in order.mock_calls] == ["bump", "set_password", "void_tokens", "delete_sessions"]

    def test_requiring_a_password_change_bumps_before_any_other_write(self, mock_db, generation):
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        with (
            patch(_PREFIX + "users_integration.require_user"),
            patch(_PREFIX + "credentials_integration.require_password_change") as require,
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user", return_value=0) as delete_sessions,
            patch(_PREFIX + "_stage_credential_changed"),
        ):
            order.attach_mock(require, "require_change")
            order.attach_mock(delete_sessions, "delete_sessions")
            account_security_service.require_managed_user_password_change(OTHER_USER_ID, mock_db)

        assert [call[0] for call in order.mock_calls] == ["bump", "require_change", "delete_sessions"]

    def test_signing_out_everywhere_bumps_before_the_commit(self, mock_db, generation):
        order = MagicMock()
        order.attach_mock(generation.stage_bump, "bump")
        order.attach_mock(mock_db.commit, "commit")
        with (
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user", return_value=2) as delete_sessions,
            patch(_PREFIX + "_stage_sessions_revoked"),
        ):
            order.attach_mock(delete_sessions, "delete_sessions")
            account_security_service.sign_out_everywhere(USER_ID, mock_db)

        assert [call[0] for call in order.mock_calls] == ["bump", "delete_sessions", "commit"]
        generation.stage_bump.assert_called_once_with(USER_ID, mock_db)

    def test_signing_out_other_devices_does_not_bump(self, mock_db, generation):
        with (
            patch(_PREFIX + "sessions_integration.delete_sessions_by_user", return_value=2),
            patch(_PREFIX + "_stage_sessions_revoked"),
        ):
            account_security_service.stage_delete_other_user_sessions(USER_ID, _SID, mock_db)

        generation.stage_bump.assert_not_called()
