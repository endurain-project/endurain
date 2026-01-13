"""Tests for IdP link tokens CRUD operations."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

import auth.idp_link_tokens.crud as idp_link_token_crud
import auth.idp_link_tokens.models as idp_link_token_models
import auth.idp_link_tokens.schema as idp_link_token_schema


class TestGetIdpLinkTokenById:
    """Test suite for get_idp_link_token_by_id function."""

    def test_get_token_success(self, mock_db):
        """Test successful retrieval of valid IdP link token."""
        # Arrange
        token_id = "test_token_12345678"
        mock_token = MagicMock(spec=idp_link_token_models.IdpLinkToken)
        mock_token.id = token_id
        mock_token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        mock_token.used = False

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_token

        # Act
        result = idp_link_token_crud.get_idp_link_token_by_id(token_id, mock_db)

        # Assert
        assert result == mock_token
        mock_db.query.assert_called_once_with(idp_link_token_models.IdpLinkToken)

    def test_get_token_not_found(self, mock_db):
        """Test IdP link token not found returns None."""
        # Arrange
        token_id = "nonexistent_token"

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = None

        # Act
        result = idp_link_token_crud.get_idp_link_token_by_id(token_id, mock_db)

        # Assert
        assert result is None

    def test_get_token_expired(self, mock_db):
        """Test expired IdP link token returns None."""
        # Arrange
        token_id = "expired_token_12345678"
        mock_token = MagicMock(spec=idp_link_token_models.IdpLinkToken)
        mock_token.id = token_id
        mock_token.expires_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_token.used = False

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_token

        # Act
        result = idp_link_token_crud.get_idp_link_token_by_id(token_id, mock_db)

        # Assert
        assert result is None

    def test_get_token_already_used(self, mock_db):
        """Test already used IdP link token returns None (replay protection)."""
        # Arrange
        token_id = "used_token_12345678"
        mock_token = MagicMock(spec=idp_link_token_models.IdpLinkToken)
        mock_token.id = token_id
        mock_token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)
        mock_token.used = True

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_token

        # Act
        result = idp_link_token_crud.get_idp_link_token_by_id(token_id, mock_db)

        # Assert
        assert result is None

    def test_get_token_database_error(self, mock_db):
        """Test database error raises HTTPException."""
        # Arrange
        token_id = "error_token"
        mock_db.query.side_effect = Exception("Database connection error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_link_token_crud.get_idp_link_token_by_id(token_id, mock_db)

        assert exc_info.value.status_code == 500
        assert "Failed to retrieve link token" in exc_info.value.detail


class TestCreateIdpLinkToken:
    """Test suite for create_idp_link_token function."""

    def test_create_token_success(self, mock_db):
        """Test successful IdP link token creation."""
        # Arrange
        token_id = "new_token_12345678"
        user_id = 1
        idp_id = 2
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(seconds=60)

        token_data = idp_link_token_schema.IdpLinkTokenCreate(
            id=token_id,
            user_id=user_id,
            idp_id=idp_id,
            created_at=created_at,
            expires_at=expires_at,
            used=False,
            ip_address="192.168.1.1",
        )

        with patch(
            "auth.idp_link_tokens.crud.idp_link_token_models.IdpLinkToken"
        ) as mock_model:
            mock_token = MagicMock()
            mock_model.return_value = mock_token

            # Act
            result = idp_link_token_crud.create_idp_link_token(token_data, mock_db)

            # Assert
            mock_model.assert_called_once()
            mock_db.add.assert_called_once_with(mock_token)
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once_with(mock_token)
            assert result == mock_token

    def test_create_token_without_ip_address(self, mock_db):
        """Test IdP link token creation without IP address."""
        # Arrange
        token_id = "token_no_ip_12345678"
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + timedelta(seconds=60)

        token_data = idp_link_token_schema.IdpLinkTokenCreate(
            id=token_id,
            user_id=1,
            idp_id=2,
            created_at=created_at,
            expires_at=expires_at,
            used=False,
            ip_address=None,
        )

        with patch(
            "auth.idp_link_tokens.crud.idp_link_token_models.IdpLinkToken"
        ) as mock_model:
            mock_token = MagicMock()
            mock_model.return_value = mock_token

            # Act
            result = idp_link_token_crud.create_idp_link_token(token_data, mock_db)

            # Assert
            mock_model.assert_called_once()
            mock_db.add.assert_called_once_with(mock_token)
            assert result == mock_token

    def test_create_token_database_error(self, mock_db):
        """Test database error during token creation raises HTTPException."""
        # Arrange
        created_at = datetime.now(timezone.utc)
        token_data = idp_link_token_schema.IdpLinkTokenCreate(
            id="error_token",
            user_id=1,
            idp_id=2,
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=60),
            used=False,
            ip_address=None,
        )

        mock_db.add.side_effect = Exception("Database insert error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_link_token_crud.create_idp_link_token(token_data, mock_db)

        assert exc_info.value.status_code == 500
        assert "Failed to create link token" in exc_info.value.detail
        mock_db.rollback.assert_called_once()


class TestMarkTokenAsUsed:
    """Test suite for mark_token_as_used function."""

    def test_mark_token_as_used_success(self, mock_db):
        """Test successful marking of token as used."""
        # Arrange
        token_id = "token_to_mark_12345678"
        mock_token = MagicMock(spec=idp_link_token_models.IdpLinkToken)
        mock_token.id = token_id
        mock_token.used = False

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_token

        # Act
        idp_link_token_crud.mark_token_as_used(token_id, mock_db)

        # Assert
        assert mock_token.used is True
        mock_db.commit.assert_called_once()

    def test_mark_token_not_found(self, mock_db):
        """Test marking nonexistent token does nothing."""
        # Arrange
        token_id = "nonexistent_token"

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = None

        # Act
        idp_link_token_crud.mark_token_as_used(token_id, mock_db)

        # Assert
        mock_db.commit.assert_not_called()

    def test_mark_token_database_error(self, mock_db):
        """Test database error during mark raises HTTPException."""
        # Arrange
        token_id = "error_token"
        mock_token = MagicMock(spec=idp_link_token_models.IdpLinkToken)
        mock_token.id = token_id

        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_token
        mock_db.commit.side_effect = Exception("Database commit error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_link_token_crud.mark_token_as_used(token_id, mock_db)

        assert exc_info.value.status_code == 500
        assert "Failed to mark token as used" in exc_info.value.detail
        mock_db.rollback.assert_called_once()


class TestDeleteExpiredTokens:
    """Test suite for delete_expired_tokens function."""

    def test_delete_expired_tokens_success(self, mock_db):
        """Test successful deletion of expired tokens."""
        # Arrange
        num_deleted = 5
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.delete.return_value = num_deleted

        # Act
        result = idp_link_token_crud.delete_expired_tokens(mock_db)

        # Assert
        assert result == num_deleted
        mock_db.commit.assert_called_once()

    def test_delete_expired_tokens_none_found(self, mock_db):
        """Test deletion when no expired tokens exist."""
        # Arrange
        num_deleted = 0
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.delete.return_value = num_deleted

        # Act
        result = idp_link_token_crud.delete_expired_tokens(mock_db)

        # Assert
        assert result == 0
        mock_db.commit.assert_called_once()

    def test_delete_expired_tokens_database_error(self, mock_db):
        """Test database error during deletion returns 0."""
        # Arrange
        mock_db.query.side_effect = Exception("Database error")

        # Act
        result = idp_link_token_crud.delete_expired_tokens(mock_db)

        # Assert
        assert result == 0
        mock_db.rollback.assert_called_once()
