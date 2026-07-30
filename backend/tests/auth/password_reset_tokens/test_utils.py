"""Tests for password reset token utilities."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import modules.auth.password_reset_tokens.utils as password_reset_tokens_utils


class TestUsePasswordResetToken:
    """
    Test suite for use_password_reset_token function.
    """

    @patch("modules.auth.password_reset_tokens.utils.auth_sessions_crud.delete_sessions_by_user")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.mark_user_password_reset_tokens_used")
    @patch("modules.auth.password_reset_tokens.utils.auth_credentials_crud.upsert_password_hash")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.claim_password_reset_token")
    @patch("modules.auth.password_reset_tokens.utils.auth_security_stores.clear_pending_mfa_for_user")
    def test_revokes_sessions_after_successful_reset(
        self,
        mock_clear_pending_mfa,
        mock_claim_token,
        mock_edit_password,
        mock_mark_user_tokens_used,
        mock_delete_sessions,
        mock_db,
    ):
        """
        Test password reset hashes password in auth service then deletes existing user sessions.
        """
        # Arrange
        user_id = 42
        token = "plain-reset-token"
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        mock_claim_token.return_value = user_id

        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "hashed-password"

        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12
        mock_settings.password_type = "strict"

        # Act
        with (
            patch(
                "modules.auth.password_reset_tokens.utils.server_settings_utils.get_server_settings_or_404",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth.password_reset_tokens.utils.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
        ):
            password_reset_tokens_utils.use_password_reset_token(
                token,
                "new-password",
                identity_service,
                mock_db,
            )

        # Assert
        mock_claim_token.assert_called_once_with(token_hash, mock_db)
        identity_service.validate_and_hash_password.assert_called_once_with(
            "new-password",
            8,
            "strict",
        )
        mock_edit_password.assert_called_once_with(
            user_id,
            "hashed-password",
            mock_db,
            commit=False,
        )
        mock_mark_user_tokens_used.assert_called_once_with(user_id, mock_db)
        mock_delete_sessions.assert_called_once_with(user_id, mock_db, commit=False)
        mock_db.commit.assert_called_once_with()
        mock_clear_pending_mfa.assert_called_once_with(user_id)

    @patch("modules.auth.password_reset_tokens.utils.auth_credentials_crud.upsert_password_hash")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.claim_password_reset_token")
    def test_invalid_token_raises_bad_request(
        self,
        mock_claim_token,
        mock_edit_password,
        mock_db,
    ):
        """
        Test invalid password reset token is rejected.
        """
        # Arrange
        mock_claim_token.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            password_reset_tokens_utils.use_password_reset_token(
                "plain-reset-token",
                "new-password",
                MagicMock(),
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        mock_edit_password.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.auth.password_reset_tokens.utils.auth_credentials_crud.upsert_password_hash")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.claim_password_reset_token")
    def test_weak_password_raises_422_distinct_from_invalid_token(
        self,
        mock_claim_token,
        mock_edit_password,
        mock_db,
    ):
        """
        A password-policy failure is surfaced as 422 (not 400), so callers can
        tell it apart from an invalid/expired token.
        """
        # Arrange
        mock_claim_token.return_value = 42

        identity_service = MagicMock()
        identity_service.validate_and_hash_password.side_effect = HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password is too short (got 4, need \u2265 8).",
        )

        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12
        mock_settings.password_type = "strict"

        # Act & Assert
        with (
            patch(
                "modules.auth.password_reset_tokens.utils.server_settings_utils.get_server_settings_or_404",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth.password_reset_tokens.utils.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            password_reset_tokens_utils.use_password_reset_token(
                "plain-reset-token",
                "weak",
                identity_service,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        assert exc_info.value.detail == "Password is too short (got 4, need \u2265 8)."
        mock_edit_password.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch("modules.auth.password_reset_tokens.utils.auth_security_stores.clear_pending_mfa_for_user")
    @patch("modules.auth.password_reset_tokens.utils.auth_sessions_crud.delete_sessions_by_user")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.mark_user_password_reset_tokens_used")
    @patch("modules.auth.password_reset_tokens.utils.auth_credentials_crud.upsert_password_hash")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.claim_password_reset_token")
    def test_rolls_back_when_commit_fails(
        self,
        mock_claim_token,
        mock_edit_password,
        mock_mark_user_tokens_used,
        mock_delete_sessions,
        mock_clear_pending_mfa,
        mock_db,
    ):
        """
        Test failed reset transaction rolls back database changes.
        """
        # Arrange
        mock_claim_token.return_value = 42
        mock_db.commit.side_effect = SQLAlchemyError("commit failed")

        identity_service = MagicMock()
        identity_service.validate_and_hash_password.return_value = "hashed-password"
        mock_user = MagicMock()
        mock_user.access_type = "regular"
        mock_settings = MagicMock()
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12
        mock_settings.password_type = "strict"

        # Act & Assert
        with (
            patch(
                "modules.auth.password_reset_tokens.utils.server_settings_utils.get_server_settings_or_404",
                return_value=mock_settings,
            ),
            patch(
                "modules.auth.password_reset_tokens.utils.users_utils.get_user_by_id_or_404",
                return_value=mock_user,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            password_reset_tokens_utils.use_password_reset_token(
                "plain-reset-token",
                "new-password",
                identity_service,
                mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_edit_password.assert_called_once()
        mock_mark_user_tokens_used.assert_called_once()
        mock_delete_sessions.assert_called_once()
        mock_db.rollback.assert_called_once_with()
        mock_clear_pending_mfa.assert_not_called()


class TestCreatePasswordResetTokenUtils:
    """Test suite for the create_password_reset_token utility function."""

    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.create_password_reset_token")
    @patch("modules.auth.password_reset_tokens.utils.core_apprise.generate_token_and_hash")
    def test_returns_plaintext_token_not_hash(self, mock_gen, mock_create, mock_db):
        """
        Returns the plaintext token; only the hash is persisted.
        """
        # Arrange
        mock_gen.return_value = ("plain-token-123", "sha256-hash-xyz")

        # Act
        result = password_reset_tokens_utils.create_password_reset_token(user_id=1, db=mock_db)

        # Assert
        assert result == "plain-token-123"
        mock_create.assert_called_once()
        # Verify the schema object passed to crud has the hash, not the token
        schema_obj = mock_create.call_args.args[0]
        assert schema_obj.token_hash == "sha256-hash-xyz"
        assert schema_obj.user_id == 1
        assert schema_obj.used is False

    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.create_password_reset_token")
    @patch("modules.auth.password_reset_tokens.utils.core_apprise.generate_token_and_hash")
    def test_crud_error_propagates(self, mock_gen, mock_create, mock_db):
        """
        HTTPException from the CRUD layer propagates to the caller.
        """
        # Arrange
        mock_gen.return_value = ("token", "hash")
        mock_create.side_effect = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            password_reset_tokens_utils.create_password_reset_token(user_id=1, db=mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestSendPasswordResetEmail:
    """Test suite for the send_password_reset_email utility function."""

    @pytest.mark.asyncio
    async def test_raises_503_when_email_service_not_configured(self, mock_db):
        """
        Raises HTTP 503 immediately when the email service is not
        configured, without touching the database.
        """
        # Arrange
        mock_email_service = MagicMock()
        mock_email_service.is_configured.return_value = False

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await password_reset_tokens_utils.send_password_reset_email("user@example.com", mock_email_service, mock_db)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @pytest.mark.asyncio
    @patch("modules.auth.password_reset_tokens.utils.users_crud.get_user_by_email")
    async def test_returns_true_for_unknown_email(self, mock_get_user, mock_db):
        """
        Returns True without error when the email is not registered,
        preventing user enumeration.
        """
        # Arrange
        mock_email_service = MagicMock()
        mock_email_service.is_configured.return_value = True
        mock_get_user.return_value = None

        # Act
        result = await password_reset_tokens_utils.send_password_reset_email(
            "nobody@example.com", mock_email_service, mock_db
        )

        # Assert
        assert result is True
        mock_email_service.send_email.assert_not_called()

    @pytest.mark.asyncio
    @patch("modules.auth.password_reset_tokens.utils.users_crud.get_user_by_email")
    async def test_returns_true_for_inactive_user(self, mock_get_user, mock_db):
        """
        Returns True without sending an email when the user is inactive,
        preventing user enumeration.
        """
        # Arrange
        mock_email_service = MagicMock()
        mock_email_service.is_configured.return_value = True
        mock_user = MagicMock()
        mock_user.active = False
        mock_get_user.return_value = mock_user

        # Act
        result = await password_reset_tokens_utils.send_password_reset_email(
            "inactive@example.com", mock_email_service, mock_db
        )

        # Assert
        assert result is True
        mock_email_service.send_email.assert_not_called()

    @pytest.mark.asyncio
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.create_password_reset_token")
    @patch("modules.auth.password_reset_tokens.utils.core_apprise.generate_token_and_hash")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_email_messages.get_password_reset_email")
    @patch("modules.auth.password_reset_tokens.utils.core_i18n.normalize_locale")
    @patch("modules.auth.password_reset_tokens.utils.users_crud.get_user_by_email")
    async def test_sends_email_and_returns_true_for_active_user(
        self,
        mock_get_user,
        mock_normalize_locale,
        mock_get_email,
        mock_gen,
        mock_create_token_crud,
        mock_db,
    ):
        """
        Sends an email and returns True for a valid active user.
        """
        # Arrange
        mock_email_service = MagicMock()
        mock_email_service.is_configured.return_value = True
        mock_email_service.frontend_host = "https://app.example.com"
        mock_email_service.send_email = AsyncMock(return_value=True)

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.name = "Alice"
        mock_user.active = True
        mock_user.preferred_language = "en"
        mock_get_user.return_value = mock_user

        mock_normalize_locale.return_value = "en"
        mock_get_email.return_value = (
            "Reset your password",
            "<p>Reset</p>",
            "Reset",
        )
        mock_gen.return_value = ("raw-token", "hash")

        # Act
        result = await password_reset_tokens_utils.send_password_reset_email(
            "alice@example.com", mock_email_service, mock_db
        )

        # Assert
        assert result is True
        mock_email_service.send_email.assert_called_once()

    @pytest.mark.asyncio
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.create_password_reset_token")
    @patch("modules.auth.password_reset_tokens.utils.core_apprise.generate_token_and_hash")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_email_messages.get_password_reset_email")
    @patch("modules.auth.password_reset_tokens.utils.core_i18n.normalize_locale")
    @patch("modules.auth.password_reset_tokens.utils.users_crud.get_user_by_email")
    async def test_returns_false_when_email_send_fails(
        self,
        mock_get_user,
        mock_normalize_locale,
        mock_get_email,
        mock_gen,
        mock_create_token_crud,
        mock_db,
    ):
        """
        Returns False when the email service fails to dispatch the
        message.
        """
        # Arrange
        mock_email_service = MagicMock()
        mock_email_service.is_configured.return_value = True
        mock_email_service.frontend_host = "https://app.example.com"
        mock_email_service.send_email = AsyncMock(return_value=False)

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.name = "Bob"
        mock_user.active = True
        mock_user.preferred_language = "en"
        mock_get_user.return_value = mock_user

        mock_normalize_locale.return_value = "en"
        mock_get_email.return_value = ("Subject", "<p></p>", "")
        mock_gen.return_value = ("raw-token", "hash")

        # Act
        result = await password_reset_tokens_utils.send_password_reset_email(
            "bob@example.com", mock_email_service, mock_db
        )

        # Assert
        assert result is False


class TestDeleteInvalidTokensFromDb:
    """Test suite for delete_invalid_tokens_from_db function."""

    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.delete_expired_password_reset_tokens")
    @patch("modules.auth.password_reset_tokens.utils.SessionLocal")
    def test_calls_delete_expired_tokens_with_db_session(self, mock_session_local, mock_delete):
        """
        Opens a SessionLocal context manager and delegates to the
        CRUD delete function.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_session_local.return_value.__exit__.return_value = False
        mock_delete.return_value = 0

        # Act
        password_reset_tokens_utils.delete_invalid_tokens_from_db()

        # Assert
        mock_delete.assert_called_once_with(mock_db)

    @patch("modules.auth.password_reset_tokens.utils.core_logger.print_to_log_and_console")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.delete_expired_password_reset_tokens")
    @patch("modules.auth.password_reset_tokens.utils.SessionLocal")
    def test_logs_when_expired_tokens_deleted(self, mock_session_local, mock_delete, mock_log):
        """
        Logs a message when at least one expired token is deleted.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_session_local.return_value.__exit__.return_value = False
        mock_delete.return_value = 3

        # Act
        password_reset_tokens_utils.delete_invalid_tokens_from_db()

        # Assert
        mock_log.assert_called_once()
        log_msg = mock_log.call_args.args[0]
        assert "3" in log_msg

    @patch("modules.auth.password_reset_tokens.utils.core_logger.print_to_log_and_console")
    @patch("modules.auth.password_reset_tokens.utils.password_reset_tokens_crud.delete_expired_password_reset_tokens")
    @patch("modules.auth.password_reset_tokens.utils.SessionLocal")
    def test_does_not_log_when_nothing_deleted(self, mock_session_local, mock_delete, mock_log):
        """
        Does not log when no expired tokens are found.
        """
        # Arrange
        mock_db = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db
        mock_session_local.return_value.__exit__.return_value = False
        mock_delete.return_value = 0

        # Act
        password_reset_tokens_utils.delete_invalid_tokens_from_db()

        # Assert
        mock_log.assert_not_called()
