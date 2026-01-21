import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import users.users_sessions.rotated_refresh_tokens.crud as rotated_token_crud
import users.users_sessions.rotated_refresh_tokens.schema as rotated_token_schema
import users.users_sessions.rotated_refresh_tokens.models as rotated_token_models


class TestGetRotatedTokenByHash:
    """
    Test suite for get_rotated_token_by_hash function.
    """

    def test_get_rotated_token_by_hash_success(self, mock_db):
        """
        Test successful retrieval of rotated token by hash.
        """
        # Arrange
        hashed_token = "hashed-token-value"
        mock_token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result

        # Act
        result = rotated_token_crud.get_rotated_token_by_hash(hashed_token, mock_db)

        # Assert
        assert result == mock_token
        mock_db.execute.assert_called_once()

    def test_get_rotated_token_by_hash_not_found(self, mock_db):
        """
        Test retrieval when token does not exist.
        """
        # Arrange
        hashed_token = "nonexistent-token"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = rotated_token_crud.get_rotated_token_by_hash(hashed_token, mock_db)

        # Assert
        assert result is None

    def test_get_rotated_token_by_hash_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        hashed_token = "hashed-token-value"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            rotated_token_crud.get_rotated_token_by_hash(hashed_token, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateRotatedToken:
    """
    Test suite for create_rotated_token function.
    """

    def test_create_rotated_token_success(self, mock_db):
        """
        Test successful rotated token creation.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        token_data = rotated_token_schema.RotatedRefreshTokenCreate(
            token_family_id="test-family-id",
            hashed_token="hashed-token-value",
            rotation_count=0,
            rotated_at=now,
            expires_at=now + timedelta(seconds=60),
        )

        mock_db_token = MagicMock(spec=rotated_token_models.RotatedRefreshToken)

        with patch.object(
            rotated_token_models,
            "RotatedRefreshToken",
            return_value=mock_db_token,
        ):
            # Act
            result = rotated_token_crud.create_rotated_token(token_data, mock_db)

            # Assert
            assert result == mock_db_token
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_rotated_token_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        now = datetime.now(timezone.utc)
        token_data = rotated_token_schema.RotatedRefreshTokenCreate(
            token_family_id="test-family-id",
            hashed_token="hashed-token-value",
            rotation_count=0,
            rotated_at=now,
            expires_at=now + timedelta(seconds=60),
        )

        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            rotated_token_crud.create_rotated_token(token_data, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteExpiredTokens:
    """
    Test suite for delete_expired_tokens function.
    """

    def test_delete_expired_tokens_success(self, mock_db):
        """
        Test successful deletion of expired tokens.
        """
        # Arrange
        cutoff_time = datetime.now(timezone.utc)
        mock_result = MagicMock()
        mock_result.rowcount = 10
        mock_db.execute.return_value = mock_result

        # Act
        result = rotated_token_crud.delete_expired_tokens(cutoff_time, mock_db)

        # Assert
        assert result == 10
        mock_db.commit.assert_called_once()

    def test_delete_expired_tokens_none_deleted(self, mock_db):
        """
        Test when no expired tokens exist.
        """
        # Arrange
        cutoff_time = datetime.now(timezone.utc)
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = rotated_token_crud.delete_expired_tokens(cutoff_time, mock_db)

        # Assert
        assert result == 0

    def test_delete_expired_tokens_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        cutoff_time = datetime.now(timezone.utc)
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            rotated_token_crud.delete_expired_tokens(cutoff_time, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteByFamily:
    """
    Test suite for delete_by_family function.
    """

    def test_delete_by_family_success(self, mock_db):
        """
        Test successful deletion of tokens by family.
        """
        # Arrange
        token_family_id = "test-family-id"
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        # Act
        result = rotated_token_crud.delete_by_family(token_family_id, mock_db)

        # Assert
        assert result == 5
        mock_db.commit.assert_called_once()

    def test_delete_by_family_none_deleted(self, mock_db):
        """
        Test when no tokens exist for family.
        """
        # Arrange
        token_family_id = "nonexistent-family"
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = rotated_token_crud.delete_by_family(token_family_id, mock_db)

        # Assert
        assert result == 0

    def test_delete_by_family_db_error(self, mock_db):
        """
        Test exception handling when database error occurs.
        """
        # Arrange
        token_family_id = "test-family-id"
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            rotated_token_crud.delete_by_family(token_family_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
