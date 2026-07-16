"""Tests for IdP link tokens utility functions."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import modules.auth.identity_providers.link_tokens.crud as idp_link_token_crud
import modules.auth.identity_providers.link_tokens.schema as idp_link_token_schema
import modules.auth.identity_providers.link_tokens.utils as idp_link_token_utils


class TestHashIdpLinkToken:
    """Test suite for hash_idp_link_token function."""

    def test_hash_idp_link_token_uses_sha256(self):
        """Test IdP link tokens are hashed with SHA-256."""
        # Arrange
        token = "plain-link-token"
        expected = hashlib.sha256(token.encode()).hexdigest()

        # Act
        result = idp_link_token_utils.hash_idp_link_token(token)

        # Assert
        assert result == expected
        assert len(result) == 64


class TestGenerateIdpLinkToken:
    """Test suite for generate_idp_link_token function."""

    @patch("modules.auth.identity_providers.link_tokens.utils.uuid4")
    @patch("modules.auth.identity_providers.link_tokens.utils.secrets.token_urlsafe")
    def test_generate_token_success(self, mock_token_urlsafe, mock_uuid4, mock_db):
        """Test successful IdP link token generation."""
        # Arrange
        user_id = 1
        idp_id = 2
        ip_address = "192.168.1.1"
        plaintext_token = "plain-generated-token"
        token_hash = hashlib.sha256(plaintext_token.encode()).hexdigest()
        token_id = "11111111-1111-4111-8111-111111111111"
        mock_token_urlsafe.return_value = plaintext_token
        mock_uuid4.return_value = token_id

        mock_db_token = MagicMock()
        mock_db_token.id = token_id
        mock_db_token.expires_at = datetime.now(UTC) + timedelta(seconds=60)

        with patch.object(
            idp_link_token_crud,
            "create_idp_link_token",
            return_value=mock_db_token,
        ) as mock_create:
            # Act
            result = idp_link_token_utils.generate_idp_link_token(user_id, idp_id, ip_address, mock_db)

            # Assert
            assert isinstance(result, idp_link_token_schema.IdpLinkTokenResponse)
            assert result.token == plaintext_token
            assert result.token != mock_db_token.id
            assert result.expires_at == mock_db_token.expires_at
            mock_create.assert_called_once()

            call_args = mock_create.call_args[0]
            token_data = call_args[0]
            assert isinstance(token_data, idp_link_token_schema.IdpLinkTokenCreate)
            assert token_data.id == token_id
            assert token_data.token_hash == token_hash
            assert token_data.user_id == user_id
            assert token_data.idp_id == idp_id
            assert token_data.ip_address == ip_address
            assert token_data.used is False

    def test_generate_token_expiry_is_60_seconds(self, mock_db):
        """Test that generated token expires in 60 seconds."""
        # Arrange
        user_id = 1
        idp_id = 2

        def capture_token_data(token_data, db):
            mock_token = MagicMock()
            mock_token.id = token_data.id
            mock_token.expires_at = token_data.expires_at
            return mock_token

        with patch.object(
            idp_link_token_crud,
            "create_idp_link_token",
            side_effect=capture_token_data,
        ) as mock_create:
            # Act
            before_generate = datetime.now(UTC)
            idp_link_token_utils.generate_idp_link_token(user_id, idp_id, None, mock_db)
            after_generate = datetime.now(UTC)

            # Assert
            call_args = mock_create.call_args[0]
            token_data = call_args[0]
            expected_expiry_min = before_generate + timedelta(seconds=59)
            expected_expiry_max = after_generate + timedelta(seconds=61)

            assert token_data.expires_at >= expected_expiry_min
            assert token_data.expires_at <= expected_expiry_max


class TestDeleteIdpLinkExpiredTokensFromDb:
    """Test suite for delete_idp_link_expired_tokens_from_db function."""

    def test_delete_expired_tokens_with_deletions(self):
        """Test cleanup when expired tokens exist."""
        # Arrange
        mock_db = MagicMock()

        with (
            patch("modules.auth.identity_providers.link_tokens.utils.core_database.SessionLocal") as mock_session_local,
            patch.object(idp_link_token_crud, "delete_expired_tokens", return_value=5) as mock_delete,
        ):
            mock_session_local.return_value.__enter__.return_value = mock_db

            # Act
            idp_link_token_utils.delete_idp_link_expired_tokens_from_db()

            # Assert
            mock_delete.assert_called_once_with(mock_db)
            mock_session_local.assert_called_once()

    def test_delete_expired_tokens_no_deletions(self):
        """Test cleanup when no expired tokens exist."""
        # Arrange
        mock_db = MagicMock()

        with (
            patch("modules.auth.identity_providers.link_tokens.utils.core_database.SessionLocal") as mock_session_local,
            patch.object(idp_link_token_crud, "delete_expired_tokens", return_value=0) as mock_delete,
        ):
            mock_session_local.return_value.__enter__.return_value = mock_db

            # Act
            idp_link_token_utils.delete_idp_link_expired_tokens_from_db()

            # Assert
            mock_delete.assert_called_once_with(mock_db)
