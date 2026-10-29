"""Tests for password-reset workflows after their move to service.py."""

import hashlib
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.state_memory import MemoryState
from jasil.providers import StateBackendUnavailableError

import core.exceptions as core_exceptions
import modules.auth.password_reset_tokens.service as password_reset_service


class TestUsePasswordResetToken:
    @patch("modules.auth.password_reset_tokens.service.mfa_integration.clear_pending_mfa_for_user")
    @patch("modules.auth.password_reset_tokens.service.sessions_integration.delete_sessions_by_user")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.mark_user_password_reset_tokens_used")
    @patch("modules.auth.password_reset_tokens.service.credentials_integration.set_local_password_hash")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token")
    def test_password_and_sessions_commit_before_pending_mfa_is_cleared(
        self, claim, set_password, mark_tokens, delete_sessions, clear_pending, mock_db
    ):
        user = MagicMock(access_type="regular")
        settings = MagicMock()
        claim.return_value = 42
        order = MagicMock()
        order.attach_mock(set_password, "password")
        order.attach_mock(mark_tokens, "tokens")
        order.attach_mock(delete_sessions, "sessions")
        order.attach_mock(mock_db.commit, "commit")
        order.attach_mock(clear_pending, "clear_pending")
        with (
            patch(
                "modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings",
                return_value=settings,
            ),
            patch("modules.auth.password_reset_tokens.service.users_integration.require_user", return_value=user),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.validate_and_hash_password_for_user",
                return_value="hashed",
            ) as hash_password,
        ):
            password_reset_service.use_password_reset_token("plain", "new password", mock_db)

        claim.assert_called_once_with(hashlib.sha256(b"plain").hexdigest(), mock_db)
        hash_password.assert_called_once_with(settings, "regular", "new password", mock_db)
        assert [call[0] for call in order.mock_calls] == [
            "password",
            "tokens",
            "sessions",
            "commit",
            "clear_pending",
        ]
        clear_pending.assert_called_once_with(42)

    @patch(
        "modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token", return_value=None
    )
    def test_invalid_token_is_a_domain_error(self, _claim, mock_db):
        with pytest.raises(core_exceptions.InvalidInputError, match="Invalid or expired"):
            password_reset_service.use_password_reset_token("invalid", "replacement", mock_db)
        mock_db.commit.assert_not_called()

    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.claim_password_reset_token", return_value=42)
    def test_password_policy_error_preserves_422(self, _claim, mock_db):
        with (
            patch("modules.auth.password_reset_tokens.service.server_settings_integration.get_server_settings"),
            patch(
                "modules.auth.password_reset_tokens.service.users_integration.require_user", return_value=MagicMock()
            ),
            patch(
                "modules.auth.password_reset_tokens.service.credentials_integration.validate_and_hash_password_for_user",
                side_effect=core_exceptions.InvalidInputError("Password is too short"),
            ),
            pytest.raises(password_reset_service.PasswordPolicyError) as exc_info,
        ):
            password_reset_service.use_password_reset_token("valid", "weak", mock_db)
        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "Password is too short"
        mock_db.commit.assert_not_called()


class TestCreatePasswordResetToken:
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.create_password_reset_token")
    @patch("modules.auth.password_reset_tokens.service.password_reset_crud.mark_user_password_reset_tokens_used")
    @patch("modules.auth.password_reset_tokens.service.token_hashing.generate_token_and_hash")
    def test_stages_replacement_and_commits(self, generate, invalidate, create, mock_db):
        generate.return_value = ("plain", "hashed")

        assert password_reset_service.create_password_reset_token(7, mock_db) == "plain"

        invalidate.assert_called_once_with(7, mock_db)
        token = create.call_args.args[0]
        assert token.user_id == 7
        assert token.token_hash == "hashed"
        mock_db.commit.assert_called_once()


class TestRequestPasswordReset:
    @patch(
        "modules.auth.password_reset_tokens.service.server_settings_integration.is_mail_configured", return_value=False
    )
    def test_mail_unavailable_is_a_domain_error(self, _configured, mock_db):
        with pytest.raises(core_exceptions.ServiceUnavailableError):
            password_reset_service.request_password_reset_email("user@example.com", MemoryState(), mock_db)

    @patch(
        "modules.auth.password_reset_tokens.service.password_reset_event_publishers.publish_password_reset_requested"
    )
    @patch("modules.auth.password_reset_tokens.service.users_integration.get_user_by_email")
    @patch(
        "modules.auth.password_reset_tokens.service.server_settings_integration.is_mail_configured", return_value=True
    )
    def test_unknown_or_inactive_users_are_not_disclosed(self, _configured, get_user, publish, mock_db):
        get_user.return_value = None
        password_reset_service.request_password_reset_email("nobody@example.com", MemoryState(), mock_db)
        get_user.return_value = MagicMock(active=False)
        password_reset_service.request_password_reset_email("inactive@example.com", MemoryState(), mock_db)
        publish.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch(
        "modules.auth.password_reset_tokens.service.password_reset_event_publishers.publish_password_reset_requested"
    )
    @patch(
        "modules.auth.password_reset_tokens.service.users_integration.get_user_by_email",
        return_value=MagicMock(id=9, active=True),
    )
    @patch(
        "modules.auth.password_reset_tokens.service.server_settings_integration.is_mail_configured", return_value=True
    )
    def test_active_user_event_is_committed(self, _configured, _user, publish, mock_db):
        password_reset_service.request_password_reset_email("user@example.com", MemoryState(), mock_db)
        publish.assert_called_once_with(9, mock_db)
        mock_db.commit.assert_called_once()


class TestPasswordResetCooldown:
    @pytest.fixture(autouse=True)
    def _mail_and_user(self):
        with (
            patch(
                "modules.auth.password_reset_tokens.service.server_settings_integration.is_mail_configured",
                return_value=True,
            ),
            patch(
                "modules.auth.password_reset_tokens.service.users_integration.get_user_by_email",
                side_effect=lambda email, db: MagicMock(id=9 if email == "a@example.com" else 10, active=True),
            ),
            patch(
                "modules.auth.password_reset_tokens.service.password_reset_event_publishers"
                ".publish_password_reset_requested"
            ) as publish,
        ):
            self.publish = publish
            yield

    def test_an_address_is_mailed_once_per_cooldown(self, mock_db):
        state = MemoryState()

        password_reset_service.request_password_reset_email("a@example.com", state, mock_db)
        password_reset_service.request_password_reset_email("a@example.com", state, mock_db)

        self.publish.assert_called_once_with(9, mock_db)

    def test_each_account_has_its_own_cooldown(self, mock_db):
        state = MemoryState()

        password_reset_service.request_password_reset_email("a@example.com", state, mock_db)
        password_reset_service.request_password_reset_email("b@example.com", state, mock_db)

        assert self.publish.call_count == 2

    def test_an_unreachable_state_store_skips_the_email_without_failing_the_request(self, mock_db):
        broken = MagicMock()
        broken.set_if_absent.side_effect = StateBackendUnavailableError("down")

        password_reset_service.request_password_reset_email("a@example.com", broken, mock_db)

        self.publish.assert_not_called()


class TestPreparePasswordResetEmail:
    @patch("modules.auth.password_reset_tokens.service.users_integration.get_user", return_value=None)
    def test_missing_user_is_skipped(self, _user, mock_db):
        assert password_reset_service.prepare_password_reset_email(5, "https://example.test", mock_db) is None

    @patch("modules.auth.password_reset_tokens.service.password_reset_email_messages.get_password_reset_email")
    @patch("modules.auth.password_reset_tokens.service.create_password_reset_token", return_value="plain-token")
    @patch(
        "modules.auth.password_reset_tokens.service.users_integration.get_user",
        return_value=MagicMock(id=5, active=True, preferred_language="en", name="Test", email="test@example.test"),
    )
    def test_prepares_localized_content_with_reset_link(self, _user, _token, build_email, mock_db):
        build_email.return_value = ("subject", "html", "text")

        result = password_reset_service.prepare_password_reset_email(5, "https://example.test", mock_db)

        assert result == ("test@example.test", "subject", "html", "text")
        assert "reset-password?token=plain-token" in build_email.call_args.args[1]
