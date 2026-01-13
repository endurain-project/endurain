"""Tests for IdP link tokens utility functions."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import auth.idp_link_tokens.utils as idp_link_token_utils
import auth.idp_link_tokens.crud as idp_link_token_crud
import auth.idp_link_tokens.schema as idp_link_token_schema


class TestGenerateIdpLinkToken:
    """Test suite for generate_idp_link_token function."""

    def test_generate_token_success(self, mock_db):
        """Test successful IdP link token generation."""
        # Arrange
        user_id = 1
        idp_id = 2
        ip_address = "192.168.1.1"

        mock_db_token = MagicMock()
        mock_db_token.id = "generated_token_12345678"
        mock_db_token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)

        with patch.object(
            idp_link_token_crud, "create_idp_link_token", return_value=mock_db_token
        ) as mock_create:
            # Act
            result = idp_link_token_utils.generate_idp_link_token(
                user_id, idp_id, ip_address, mock_db
            )

            # Assert
            assert isinstance(result, idp_link_token_schema.IdpLinkTokenResponse)
            assert result.token == mock_db_token.id
            assert result.expires_at == mock_db_token.expires_at
            mock_create.assert_called_once()

            # Verify create_idp_link_token was called with correct schema
            call_args = mock_create.call_args[0]
            token_data = call_args[0]
            assert isinstance(token_data, idp_link_token_schema.IdpLinkTokenCreate)
            assert token_data.user_id == user_id
            assert token_data.idp_id == idp_id
            assert token_data.ip_address == ip_address
            assert token_data.used is False

    def test_generate_token_without_ip_address(self, mock_db):
        """Test IdP link token generation without IP address."""
        # Arrange
        user_id = 1
        idp_id = 2
        ip_address = None

        mock_db_token = MagicMock()
        mock_db_token.id = "token_no_ip_12345678"
        mock_db_token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)

        with patch.object(
            idp_link_token_crud, "create_idp_link_token", return_value=mock_db_token
        ) as mock_create:
            # Act
            result = idp_link_token_utils.generate_idp_link_token(
                user_id, idp_id, ip_address, mock_db
            )

            # Assert
            assert result.token == mock_db_token.id
            call_args = mock_create.call_args[0]
            token_data = call_args[0]
            assert token_data.ip_address is None

    def test_generate_token_expiry_is_60_seconds(self, mock_db):
        """Test that generated token expires in 60 seconds."""
        # Arrange
        user_id = 1
        idp_id = 2

        mock_db_token = MagicMock()
        mock_db_token.id = "expiry_test_token"
        mock_db_token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)

        with patch.object(
            idp_link_token_crud, "create_idp_link_token", return_value=mock_db_token
        ) as mock_create:
            # Act
            before_generate = datetime.now(timezone.utc)
            idp_link_token_utils.generate_idp_link_token(user_id, idp_id, None, mock_db)
            after_generate = datetime.now(timezone.utc)

            # Assert
            call_args = mock_create.call_args[0]
            token_data = call_args[0]

            # Verify expiry is approximately 60 seconds from created_at
            expected_expiry_min = before_generate + timedelta(seconds=59)
            expected_expiry_max = after_generate + timedelta(seconds=61)

            assert token_data.expires_at >= expected_expiry_min
            assert token_data.expires_at <= expected_expiry_max

    def test_generate_token_unique_ids(self, mock_db):
        """Test that each generated token has a unique ID."""
        # Arrange
        user_id = 1
        idp_id = 2
        generated_ids = []

        def capture_token_data(token_data, db):
            mock_token = MagicMock()
            mock_token.id = token_data.id
            mock_token.expires_at = token_data.expires_at
            generated_ids.append(token_data.id)
            return mock_token

        with patch.object(
            idp_link_token_crud, "create_idp_link_token", side_effect=capture_token_data
        ):
            # Act - Generate multiple tokens
            for _ in range(5):
                idp_link_token_utils.generate_idp_link_token(
                    user_id, idp_id, None, mock_db
                )

            # Assert - All IDs should be unique
            assert len(generated_ids) == 5
            assert len(set(generated_ids)) == 5  # All unique


class TestDeleteIdpLinkExpiredTokensFromDb:
    """Test suite for delete_idp_link_expired_tokens_from_db function."""

    def test_delete_expired_tokens_with_deletions(self):
        """Test cleanup when expired tokens exist."""
        # Arrange
        num_deleted = 5
        mock_db = MagicMock()

        with patch(
            "auth.idp_link_tokens.utils.core_database.SessionLocal"
        ) as mock_session_local, patch.object(
            idp_link_token_crud, "delete_expired_tokens", return_value=num_deleted
        ) as mock_delete:
            mock_session_local.return_value.__enter__.return_value = mock_db

            # Act
            idp_link_token_utils.delete_idp_link_expired_tokens_from_db()

            # Assert
            mock_delete.assert_called_once_with(mock_db)
            mock_session_local.assert_called_once()

    def test_delete_expired_tokens_no_deletions(self):
        """Test cleanup when no expired tokens exist."""
        # Arrange
        num_deleted = 0
        mock_db = MagicMock()

        with patch(
            "auth.idp_link_tokens.utils.core_database.SessionLocal"
        ) as mock_session_local, patch.object(
            idp_link_token_crud, "delete_expired_tokens", return_value=num_deleted
        ) as mock_delete:
            mock_session_local.return_value.__enter__.return_value = mock_db

            # Act
            idp_link_token_utils.delete_idp_link_expired_tokens_from_db()

            # Assert
            mock_delete.assert_called_once_with(mock_db)

    def test_delete_expired_tokens_context_manager(self):
        """Test session context manager is properly used."""
        # Arrange
        num_deleted = 3
        mock_db = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_db
        mock_context.__exit__.return_value = None

        with patch(
            "auth.idp_link_tokens.utils.core_database.SessionLocal",
            return_value=mock_context,
        ) as mock_session_local, patch.object(
            idp_link_token_crud, "delete_expired_tokens", return_value=num_deleted
        ):
            # Act
            idp_link_token_utils.delete_idp_link_expired_tokens_from_db()

            # Assert
            mock_session_local.assert_called_once()
            mock_context.__enter__.assert_called_once()
            mock_context.__exit__.assert_called_once()
