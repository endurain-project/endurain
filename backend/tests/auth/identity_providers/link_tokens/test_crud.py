"""Tests for IdP link tokens CRUD operations."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.auth.identity_providers.link_tokens.crud as idp_link_token_crud
import modules.auth.identity_providers.link_tokens.schema as idp_link_token_schema


class TestGetIdpLinkTokenByHash:
    """Test suite for get_idp_link_token_by_hash function."""

    def test_get_token_success(self, mock_db):
        """Test successful retrieval of valid IdP link token."""
        # Arrange
        token_hash = "a" * 64
        mock_token = object()
        mock_result = mock_db.execute.return_value
        mock_result.scalar_one_or_none.return_value = mock_token

        # Act
        result = idp_link_token_crud.get_idp_link_token_by_hash(token_hash, mock_db)

        # Assert
        assert result == mock_token
        mock_db.execute.assert_called_once()

    def test_get_token_not_found(self, mock_db):
        """Test IdP link token not found returns None."""
        # Arrange
        token_hash = "b" * 64
        mock_result = mock_db.execute.return_value
        mock_result.scalar_one_or_none.return_value = None

        # Act
        result = idp_link_token_crud.get_idp_link_token_by_hash(token_hash, mock_db)

        # Assert
        assert result is None

    def test_get_token_database_error(self, mock_db):
        """Test database errors are converted to HTTPException."""
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            idp_link_token_crud.get_idp_link_token_by_hash("c" * 64, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateIdpLinkToken:
    """Test suite for create_idp_link_token function."""

    def test_create_token_success(self, mock_db):
        """Test successful IdP link token creation."""
        # Arrange
        created_at = datetime.now(UTC)
        token_data = idp_link_token_schema.IdpLinkTokenCreate(
            id="11111111-1111-4111-8111-111111111111",
            token_hash="d" * 64,
            user_id=1,
            idp_id=2,
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=60),
            used=False,
            ip_address="192.168.1.1",
        )

        with patch("modules.auth.identity_providers.link_tokens.crud.idp_link_token_models.IdpLinkToken") as mock_model:
            mock_token = MagicMock()
            mock_model.return_value = mock_token

            # Act
            result = idp_link_token_crud.create_idp_link_token(token_data, mock_db)

            # Assert
            mock_model.assert_called_once_with(**token_data.model_dump())
            mock_db.add.assert_called_once_with(mock_token)
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once_with(mock_token)
            assert result == mock_token


class TestMarkTokenAsUsed:
    """Test suite for mark_token_as_used function."""

    def test_mark_token_as_used_success(self, mock_db):
        """Test successful marking of token hash as used."""
        # Arrange
        mock_result = mock_db.execute.return_value
        mock_result.rowcount = 1

        # Act
        result = idp_link_token_crud.mark_token_as_used("e" * 64, mock_db)

        # Assert
        assert result is True
        mock_db.commit.assert_called_once()

    def test_mark_token_not_found(self, mock_db):
        """Test marking nonexistent token returns False."""
        # Arrange
        mock_result = mock_db.execute.return_value
        mock_result.rowcount = 0

        # Act
        result = idp_link_token_crud.mark_token_as_used("f" * 64, mock_db)

        # Assert
        assert result is False
        mock_db.commit.assert_called_once()


class TestDeleteExpiredTokens:
    """Test suite for delete_expired_tokens function."""

    def test_delete_expired_tokens_success(self, mock_db):
        """Test successful deletion of expired tokens."""
        # Arrange
        mock_result = mock_db.execute.return_value
        mock_result.rowcount = 5

        # Act
        result = idp_link_token_crud.delete_expired_tokens(mock_db)

        # Assert
        assert result == 5
        mock_db.commit.assert_called_once()

    def test_delete_expired_tokens_none_found(self, mock_db):
        """Test deletion when no expired tokens exist."""
        # Arrange
        mock_result = mock_db.execute.return_value
        mock_result.rowcount = 0

        # Act
        result = idp_link_token_crud.delete_expired_tokens(mock_db)

        # Assert
        assert result == 0
        mock_db.commit.assert_called_once()
