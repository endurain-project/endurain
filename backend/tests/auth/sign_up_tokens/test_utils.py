"""Tests for sign-up token utility functions."""

import hashlib
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest
from fastapi import HTTPException, status

import modules.auth.sign_up_tokens.utils as sign_up_tokens_utils


def _user(**overrides) -> MagicMock:
    """Build a minimal user mock."""
    user = MagicMock()
    user.id = overrides.get("id", 1)
    user.name = overrides.get("name", "Test User")
    user.username = overrides.get("username", "testuser")
    user.email = overrides.get("email", "user@example.com")
    user.preferred_language = "en"
    return user


class TestCreateSignUpTokenUtils:
    """Tests for create_sign_up_token."""

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.create_sign_up_token")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.mark_user_sign_up_tokens_used")
    @patch("modules.auth.sign_up_tokens.utils.token_hashing.generate_token_and_hash")
    def test_returns_plain_token_and_stores_only_hash(self, mock_generate, mock_invalidate, mock_create, mock_db):
        """The plain token is returned; the stored schema holds only its hash."""
        mock_generate.return_value = ("plain-token", "hashed-token")

        result = sign_up_tokens_utils.create_sign_up_token(7, mock_db)

        assert result == "plain-token"
        stored = mock_create.call_args.args[0]
        assert stored.user_id == 7
        assert stored.token_hash == "hashed-token"
        assert stored.used is False

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.create_sign_up_token")
    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_crud.mark_user_sign_up_tokens_used")
    def test_invalidates_earlier_tokens_before_creating(self, mock_invalidate, mock_create, mock_db):
        """Earlier unused tokens are invalidated before the new one is committed."""
        manager = MagicMock()
        manager.attach_mock(mock_invalidate, "invalidate")
        manager.attach_mock(mock_create, "create")

        sign_up_tokens_utils.create_sign_up_token(7, mock_db)

        assert [c[0] for c in manager.mock_calls] == ["invalidate", "create"]
        mock_invalidate.assert_called_once_with(7, mock_db)


class TestRequestEmails:
    """Tests for the request_* functions that publish email events."""

    @patch("modules.auth.sign_up_tokens.utils.core_mail.is_mail_configured", return_value=False)
    def test_not_configured_raises_503(self, _configured, mock_db):
        """Every request function raises 503 when mail is not configured."""
        for call in (
            lambda: sign_up_tokens_utils.request_sign_up_verification_email(1, mock_db),
            lambda: sign_up_tokens_utils.request_sign_up_admin_approval_emails(1, mock_db),
            lambda: sign_up_tokens_utils.request_sign_up_approved_email(1, mock_db),
        ):
            with pytest.raises(HTTPException) as exc_info:
                call()
            assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_event_publishers.publish_sign_up_verification_requested")
    @patch("modules.auth.sign_up_tokens.utils.core_mail.is_mail_configured", return_value=True)
    def test_verification_publishes_event(self, _configured, mock_publish, mock_db):
        sign_up_tokens_utils.request_sign_up_verification_email(5, mock_db)

        mock_publish.assert_called_once_with(5, mock_db)

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_event_publishers.publish_sign_up_approval_requested")
    @patch("modules.auth.sign_up_tokens.utils.users_utils.get_admin_users_or_404")
    @patch("modules.auth.sign_up_tokens.utils.core_mail.is_mail_configured", return_value=True)
    def test_admin_approval_publishes_one_event_per_admin(self, _configured, mock_admins, mock_publish, mock_db):
        mock_admins.return_value = [MagicMock(id=10), MagicMock(id=11)]

        sign_up_tokens_utils.request_sign_up_admin_approval_emails(5, mock_db)

        assert [c.args for c in mock_publish.call_args_list] == [(5, 10, mock_db), (5, 11, mock_db)]

    @patch("modules.auth.sign_up_tokens.utils.users_utils.get_admin_users_or_404")
    @patch("modules.auth.sign_up_tokens.utils.core_mail.is_mail_configured", return_value=True)
    def test_admin_approval_no_admins_raises_404(self, _configured, mock_admins, mock_db):
        mock_admins.side_effect = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No admin users found")

        with pytest.raises(HTTPException) as exc_info:
            sign_up_tokens_utils.request_sign_up_admin_approval_emails(5, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    @patch("modules.auth.sign_up_tokens.utils.sign_up_tokens_event_publishers.publish_sign_up_approved")
    @patch("modules.auth.sign_up_tokens.utils.core_mail.is_mail_configured", return_value=True)
    def test_approved_publishes_event(self, _configured, mock_publish, mock_db):
        sign_up_tokens_utils.request_sign_up_approved_email(5, mock_db)

        mock_publish.assert_called_once_with(5, mock_db)


class TestSendEmailsToUser:
    """Tests for the handler-side send functions."""

    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id", return_value=None)
    def test_missing_user_is_skipped(self, _get_user, mock_db):
        mail = MagicMock()

        assert sign_up_tokens_utils.send_sign_up_verification_email_to_user(1, mail, mock_db) is False
        assert sign_up_tokens_utils.send_sign_up_approved_email_to_user(1, mail, mock_db) is False
        assert sign_up_tokens_utils.send_sign_up_approval_request_email_to_admin(1, 2, mail, mock_db) is False
        mail.send.assert_not_called()

    @patch("modules.auth.sign_up_tokens.utils.create_sign_up_token", return_value="plain-token")
    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id")
    def test_verification_sends_link_with_token(self, mock_get_user, _create_token, mock_db):
        mock_get_user.return_value = _user(email="new@example.com")
        mail = MagicMock()

        assert sign_up_tokens_utils.send_sign_up_verification_email_to_user(1, mail, mock_db) is True

        message = mail.send.call_args.args[0]
        assert message.to == ["new@example.com"]
        assert "verify-email?token=plain-token" in message.text

    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id")
    def test_approval_request_goes_to_admin(self, mock_get_user, mock_db):
        users = {1: _user(id=1, username="newbie"), 2: _user(id=2, email="admin@example.com")}
        mock_get_user.side_effect = lambda user_id, _db: users[user_id]
        mail = MagicMock()

        assert sign_up_tokens_utils.send_sign_up_approval_request_email_to_admin(1, 2, mail, mock_db) is True

        message = mail.send.call_args.args[0]
        assert message.to == ["admin@example.com"]
        assert "newbie" in message.text

    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id")
    def test_approved_goes_to_user(self, mock_get_user, mock_db):
        mock_get_user.return_value = _user(email="ok@example.com")
        mail = MagicMock()

        assert sign_up_tokens_utils.send_sign_up_approved_email_to_user(1, mail, mock_db) is True

        assert mail.send.call_args.args[0].to == ["ok@example.com"]

    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id")
    def test_permanent_failure_is_not_retried(self, mock_get_user, mock_db):
        mock_get_user.return_value = _user()
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailError("refused", status=550)

        assert sign_up_tokens_utils.send_sign_up_approved_email_to_user(1, mail, mock_db) is False

    @patch("modules.auth.sign_up_tokens.utils.users_crud.get_user_by_id")
    def test_transient_failure_propagates_for_retry(self, mock_get_user, mock_db):
        mock_get_user.return_value = _user()
        mail = MagicMock()
        mail.send.side_effect = platform_providers.MailError("unreachable")

        with pytest.raises(platform_providers.MailError):
            sign_up_tokens_utils.send_sign_up_approved_email_to_user(1, mail, mock_db)


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

    @patch("modules.auth.sign_up_tokens.utils.logger")
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
        assert len(mock_log.method_calls) == 1


class TestDeleteInvalidTokensFromDb:
    """Test suite for delete_invalid_tokens_from_db function."""

    @patch("modules.auth.sign_up_tokens.utils.logger")
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
        assert len(mock_log.method_calls) == 1

    @patch("modules.auth.sign_up_tokens.utils.logger")
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
