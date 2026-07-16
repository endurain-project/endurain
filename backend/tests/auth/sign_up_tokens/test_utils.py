"""Tests for sign-up token utility functions."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, status

import modules.auth.sign_up_tokens.utils as sign_up_tokens_utils


def _make_email_service(configured: bool = True) -> MagicMock:
    """Build a minimal AppriseService mock."""
    svc = MagicMock()
    svc.is_configured.return_value = configured
    svc.frontend_host = "https://endurain.example.com"
    svc.send_email = AsyncMock(return_value=True)
    return svc


class TestCreateSignUpTokenUtils:
    """Test suite for create_sign_up_token utility function."""

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.create_sign_up_token")
    @patch("modules.auth.sign_up_tokens.utils.core_apprise.generate_token_and_hash")
    def test_create_sign_up_token_returns_plain_token(
        self,
        mock_generate,
        mock_crud_create,
        mock_db,
    ):
        """Returns the plaintext token, not the hash."""
        # Arrange
        mock_generate.return_value = ("plain-token", "hashed-token")

        # Act
        result = sign_up_tokens_utils.create_sign_up_token(42, mock_db)

        # Assert
        assert result == "plain-token"
        mock_generate.assert_called_once()

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.create_sign_up_token")
    @patch("modules.auth.sign_up_tokens.utils.core_apprise.generate_token_and_hash")
    def test_create_sign_up_token_persists_to_db(
        self,
        mock_generate,
        mock_crud_create,
        mock_db,
    ):
        """CRUD create is called once with the token schema."""
        # Arrange
        mock_generate.return_value = ("plain-token", "hashed-token")

        # Act
        sign_up_tokens_utils.create_sign_up_token(7, mock_db)

        # Assert
        mock_crud_create.assert_called_once()
        _, call_db = mock_crud_create.call_args.args
        assert call_db is mock_db


class TestSendSignUpEmail:
    """Test suite for send_sign_up_email function."""

    async def test_send_sign_up_email_not_configured_raises_503(self, mock_db):
        """503 raised when email service is not configured."""
        # Arrange
        email_service = _make_email_service(configured=False)
        user = MagicMock()

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await sign_up_tokens_utils.send_sign_up_email(user, email_service, mock_db)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_email_messages.get_signup_confirmation_email")
    @patch("modules.auth.sign_up_tokens.utils.core_i18n.normalize_locale")
    @patch("modules.auth.sign_up_tokens.utils.create_sign_up_token")
    async def test_send_sign_up_email_success_sends_email(
        self,
        mock_create_token,
        mock_normalize,
        mock_get_email,
        mock_db,
    ):
        """Email is sent with localized content on success."""
        # Arrange
        email_service = _make_email_service(configured=True)
        user = MagicMock()
        user.preferred_language = "en"
        user.name = "Alice"
        user.email = "alice@example.com"
        mock_create_token.return_value = "plain-token"
        mock_normalize.return_value = "us"
        mock_get_email.return_value = ("Subject", "<html>", "text")

        # Act
        result = await sign_up_tokens_utils.send_sign_up_email(user, email_service, mock_db)

        # Assert
        assert result is True
        email_service.send_email.assert_awaited_once()
        mock_create_token.assert_called_once_with(user.id, mock_db)


class TestSendSignUpAdminApprovalEmail:
    """Test suite for send_sign_up_admin_approval_email."""

    async def test_send_sign_up_admin_approval_not_configured_503(self, mock_db):
        """503 raised when email service is not configured."""
        # Arrange
        email_service = _make_email_service(configured=False)
        user = MagicMock()

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await sign_up_tokens_utils.send_sign_up_admin_approval_email(user, email_service, mock_db)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_email_messages.get_admin_signup_notification_email")
    @patch("modules.auth.sign_up_tokens.utils.core_i18n.normalize_locale")
    @patch("modules.auth.sign_up_tokens.utils.users_utils.get_admin_users_or_404")
    async def test_send_sign_up_admin_approval_sends_to_all_admins(
        self,
        mock_get_admins,
        mock_normalize,
        mock_get_email,
        mock_db,
    ):
        """Email is sent once for each admin user."""
        # Arrange
        email_service = _make_email_service(configured=True)
        user = MagicMock()
        user.name = "NewUser"
        user.username = "newuser"
        admin1 = MagicMock()
        admin1.preferred_language = "en"
        admin1.email = "admin1@example.com"
        admin2 = MagicMock()
        admin2.preferred_language = "pt-PT"
        admin2.email = "admin2@example.com"
        mock_get_admins.return_value = [admin1, admin2]
        mock_normalize.return_value = "en"
        mock_get_email.return_value = ("Subject", "<html>", "text")

        # Act
        await sign_up_tokens_utils.send_sign_up_admin_approval_email(user, email_service, mock_db)

        # Assert
        assert email_service.send_email.await_count == 2

    @patch("modules.auth.sign_up_tokens.utils.users_utils.get_admin_users_or_404")
    async def test_send_sign_up_admin_approval_no_admins_raises_404(
        self,
        mock_get_admins,
        mock_db,
    ):
        """404 propagated when no admin users exist."""
        # Arrange
        email_service = _make_email_service(configured=True)
        user = MagicMock()
        mock_get_admins.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No admin users found",
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await sign_up_tokens_utils.send_sign_up_admin_approval_email(user, email_service, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestSendSignUpApprovalEmail:
    """Test suite for send_sign_up_approval_email function."""

    async def test_send_sign_up_approval_not_configured_raises_503(self, mock_db):
        """503 raised when email service is not configured."""
        # Arrange
        email_service = _make_email_service(configured=False)

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await sign_up_tokens_utils.send_sign_up_approval_email(1, email_service, mock_db)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id")
    async def test_send_sign_up_approval_user_not_found_raises_404(
        self,
        mock_get_user,
        mock_db,
    ):
        """404 raised when user_id does not match a user."""
        # Arrange
        email_service = _make_email_service(configured=True)
        mock_get_user.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            await sign_up_tokens_utils.send_sign_up_approval_email(99, email_service, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_email_messages.get_user_signup_approved_email")
    @patch("modules.auth.sign_up_tokens.utils.core_i18n.normalize_locale")
    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id")
    async def test_send_sign_up_approval_success_sends_email(
        self,
        mock_get_user,
        mock_normalize,
        mock_get_email,
        mock_db,
    ):
        """Approval email sent to user on success."""
        # Arrange
        email_service = _make_email_service(configured=True)
        user = MagicMock()
        user.preferred_language = "en"
        user.name = "Alice"
        user.username = "alice"
        user.email = "alice@example.com"
        mock_get_user.return_value = user
        mock_normalize.return_value = "us"
        mock_get_email.return_value = ("Subject", "<html>", "text")

        # Act
        result = await sign_up_tokens_utils.send_sign_up_approval_email(1, email_service, mock_db)

        # Assert
        assert result is True
        email_service.send_email.assert_awaited_once()


class TestUseSignUpToken:
    """Test suite for use_sign_up_token function."""

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.mark_sign_up_token_used")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.get_sign_up_token_by_hash")
    def test_use_sign_up_token_success_returns_user_id(
        self,
        mock_get_by_hash,
        mock_mark_used,
        mock_db,
    ):
        """Valid token is consumed and user_id is returned."""
        # Arrange
        plain_token = "valid-plain-token"
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        mock_token = MagicMock()
        mock_token.user_id = 42
        mock_get_by_hash.return_value = mock_token

        # Act
        result = sign_up_tokens_utils.use_sign_up_token(plain_token, mock_db)

        # Assert
        assert result == 42
        mock_get_by_hash.assert_called_once_with(token_hash, mock_db)
        mock_mark_used.assert_called_once_with(mock_token.id, mock_db)

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.mark_sign_up_token_used")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.get_sign_up_token_by_hash")
    def test_use_sign_up_token_invalid_token_raises_400(
        self,
        mock_get_by_hash,
        mock_mark_used,
        mock_db,
    ):
        """Invalid or expired token raises 400 Bad Request."""
        # Arrange
        mock_get_by_hash.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            sign_up_tokens_utils.use_sign_up_token("invalid-token", mock_db)

        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
        mock_mark_used.assert_not_called()

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.mark_sign_up_token_used")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.get_sign_up_token_by_hash")
    def test_use_sign_up_token_mark_used_http_exception_propagates(
        self,
        mock_get_by_hash,
        mock_mark_used,
        mock_db,
    ):
        """HTTPException from mark_used propagates unchanged."""
        # Arrange
        mock_token = MagicMock()
        mock_get_by_hash.return_value = mock_token
        http_err = HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DB error",
        )
        mock_mark_used.side_effect = http_err

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            sign_up_tokens_utils.use_sign_up_token("valid-token", mock_db)

        assert exc_info.value is http_err

    @patch("modules.auth.sign_up_tokens.utils.core_logger.print_to_log")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.mark_sign_up_token_used")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.get_sign_up_token_by_hash")
    def test_use_sign_up_token_unexpected_error_raises_500(
        self,
        mock_get_by_hash,
        mock_mark_used,
        mock_log,
        mock_db,
    ):
        """Unexpected exception is wrapped in 500 HTTPException."""
        # Arrange
        mock_token = MagicMock()
        mock_get_by_hash.return_value = mock_token
        mock_mark_used.side_effect = RuntimeError("unexpected")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            sign_up_tokens_utils.use_sign_up_token("valid-token", mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_log.assert_called_once()


class TestDeleteInvalidTokensFromDb:
    """Test suite for delete_invalid_tokens_from_db function."""

    @patch("modules.auth.sign_up_tokens.utils.core_logger.print_to_log_and_console")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.delete_expired_sign_up_tokens")
    @patch("modules.auth.sign_up_tokens.utils.SessionLocal")
    def test_delete_invalid_tokens_from_db_logs_on_deletion(
        self,
        mock_session_local,
        mock_delete_expired,
        mock_log,
    ):
        """Log is printed when expired tokens are deleted."""
        # Arrange
        mock_db_ctx = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db_ctx
        mock_delete_expired.return_value = 3

        # Act
        sign_up_tokens_utils.delete_invalid_tokens_from_db()

        # Assert
        mock_delete_expired.assert_called_once_with(mock_db_ctx)
        mock_log.assert_called_once()

    @patch("modules.auth.sign_up_tokens.utils.core_logger.print_to_log_and_console")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.delete_expired_sign_up_tokens")
    @patch("modules.auth.sign_up_tokens.utils.SessionLocal")
    def test_delete_invalid_tokens_from_db_no_log_when_zero(
        self,
        mock_session_local,
        mock_delete_expired,
        mock_log,
    ):
        """No log printed when zero expired tokens are found."""
        # Arrange
        mock_db_ctx = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_db_ctx
        mock_delete_expired.return_value = 0

        # Act
        sign_up_tokens_utils.delete_invalid_tokens_from_db()

        # Assert
        mock_log.assert_not_called()
