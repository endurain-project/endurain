"""Tests for password reset token CRUD operations."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import operators

import core.exceptions as core_exceptions
import modules.auth.password_reset_tokens.crud as password_reset_tokens_crud
import modules.auth.password_reset_tokens.models as password_reset_tokens_models
import modules.auth.password_reset_tokens.schema as password_reset_tokens_schema


class TestClaimPasswordResetToken:
    """Test suite for claim_password_reset_token function."""

    def test_claim_password_reset_token_success(self, mock_db):
        """Test valid password reset token is claimed atomically."""
        # Arrange
        token_hash = "hashed-token"
        mock_db.execute.return_value.scalar_one_or_none.return_value = 42

        # Act
        result = password_reset_tokens_crud.claim_password_reset_token(token_hash, mock_db)

        # Assert
        assert result == 42
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        assert any(criterion.left.name == "token_hash" and criterion.operator is operators.eq for criterion in criteria)
        assert any(criterion.left.name == "used" and criterion.operator is operators.is_ for criterion in criteria)
        assert any(criterion.left.name == "expires_at" and criterion.operator is operators.gt for criterion in criteria)
        assert [column.name for column in stmt._returning] == ["user_id"]
        mock_db.commit.assert_not_called()

    def test_claim_password_reset_token_invalid(self, mock_db):
        """Test invalid password reset token claim returns None."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = password_reset_tokens_crud.claim_password_reset_token("hashed-token", mock_db)

        # Assert
        assert result is None
        mock_db.commit.assert_not_called()


class TestMarkUserPasswordResetTokensUsed:
    """Test suite for mark_user_password_reset_tokens_used function."""

    def test_mark_user_password_reset_tokens_used_success(self, mock_db):
        """Test all unused user reset tokens are invalidated."""
        # Arrange
        user_id = 42
        mock_db.execute.return_value.rowcount = 3

        # Act
        result = password_reset_tokens_crud.mark_user_password_reset_tokens_used(user_id, mock_db)

        # Assert
        assert result == 3
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        assert any(criterion.left.name == "user_id" and criterion.operator is operators.eq for criterion in criteria)
        assert any(criterion.left.name == "used" and criterion.operator is operators.is_ for criterion in criteria)
        mock_db.commit.assert_not_called()


class TestCreatePasswordResetToken:
    """Test suite for create_password_reset_token function."""

    @patch("modules.auth.password_reset_tokens.crud.password_reset_tokens_models.PasswordResetToken")
    def test_create_token_persists_and_returns_instance(self, mock_model_cls, mock_db):
        """
        Adds the token to the database, commits, refreshes, and
        returns the ORM instance.
        """
        # Arrange
        now = datetime.now(UTC)
        mock_instance = MagicMock()
        mock_model_cls.return_value = mock_instance
        token_schema = password_reset_tokens_schema.PasswordResetToken(
            id=str(uuid4()),
            user_id=1,
            token_hash="sha256hash",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            used=False,
        )

        # Act
        password_reset_tokens_crud.create_password_reset_token(token_schema, mock_db)

        # Assert
        mock_db.add.assert_called_once_with(mock_instance)
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_instance)

    @patch("modules.auth.password_reset_tokens.crud.password_reset_tokens_models.PasswordResetToken")
    def test_create_token_adds_correct_model_instance(self, mock_model_cls, mock_db):
        """
        Verifies the ORM constructor is called with the correct
        token_hash and user_id from the schema.
        """
        # Arrange
        now = datetime.now(UTC)
        expected_hash = "sha256-expected-hash"
        mock_instance = MagicMock()
        mock_model_cls.return_value = mock_instance
        token_schema = password_reset_tokens_schema.PasswordResetToken(
            id=str(uuid4()),
            user_id=2,
            token_hash=expected_hash,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            used=False,
        )

        # Act
        password_reset_tokens_crud.create_password_reset_token(token_schema, mock_db)

        # Assert — constructor was called with the expected field values
        mock_model_cls.assert_called_once_with(
            id=token_schema.id,
            user_id=2,
            token_hash=expected_hash,
            created_at=token_schema.created_at,
            expires_at=token_schema.expires_at,
            used=False,
        )

    @patch("modules.auth.password_reset_tokens.crud.password_reset_tokens_models.PasswordResetToken")
    def test_create_token_db_error_raises_500(self, mock_model_cls, mock_db):
        """
        Raises HTTP 500 when a database error occurs.
        """
        # Arrange
        now = datetime.now(UTC)
        mock_model_cls.return_value = MagicMock()
        token_schema = password_reset_tokens_schema.PasswordResetToken(
            id=str(uuid4()),
            user_id=1,
            token_hash="hash",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            used=False,
        )
        mock_db.commit.side_effect = SQLAlchemyError("db error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            password_reset_tokens_crud.create_password_reset_token(token_schema, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetPasswordResetTokenByHash:
    """Test suite for get_password_reset_token_by_hash function."""

    def test_returns_token_when_valid_and_unexpired(self, mock_db):
        """
        Returns the ORM token object when found, unused, and not
        yet expired.
        """
        # Arrange
        mock_token = MagicMock(spec=password_reset_tokens_models.PasswordResetToken)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_token

        # Act
        result = password_reset_tokens_crud.get_password_reset_token_by_hash("some-hash", mock_db)

        # Assert
        assert result is mock_token

    def test_returns_none_when_not_found(self, mock_db):
        """
        Returns None when no matching token is found.
        """
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = password_reset_tokens_crud.get_password_reset_token_by_hash("nonexistent-hash", mock_db)

        # Assert
        assert result is None

    def test_query_filters_on_hash_used_and_expiry(self, mock_db):
        """
        Verifies the SELECT filters by token_hash, used=False,
        and expires_at > now.
        """
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        password_reset_tokens_crud.get_password_reset_token_by_hash("filter-test-hash", mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        column_names = {c.left.name for c in criteria if hasattr(c, "left")}
        assert "token_hash" in column_names
        assert "used" in column_names
        assert "expires_at" in column_names

    def test_db_error_raises_500(self, mock_db):
        """
        Raises HTTP 500 when a database error occurs.
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("db error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            password_reset_tokens_crud.get_password_reset_token_by_hash("hash", mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestMarkPasswordResetTokenUsed:
    """Test suite for mark_password_reset_token_used function."""

    def test_marks_token_used_and_returns_updated_instance(self, mock_db):
        """
        Sets used=True on the token, commits, refreshes, and
        returns the updated instance.
        """
        # Arrange
        mock_token = MagicMock(spec=password_reset_tokens_models.PasswordResetToken)
        mock_token.used = False
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_token

        # Act
        result = password_reset_tokens_crud.mark_password_reset_token_used("token-id", mock_db)

        # Assert
        assert mock_token.used is True
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_token)
        assert result is mock_token

    def test_returns_none_when_token_not_found(self, mock_db):
        """
        Returns None when no token matches the given ID.
        """
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = password_reset_tokens_crud.mark_password_reset_token_used("nonexistent-id", mock_db)

        # Assert
        assert result is None
        mock_db.commit.assert_not_called()

    def test_db_error_raises_500(self, mock_db):
        """
        Raises HTTP 500 when a database error occurs.
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("db error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            password_reset_tokens_crud.mark_password_reset_token_used("token-id", mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteExpiredPasswordResetTokens:
    """Test suite for delete_expired_password_reset_tokens function."""

    def test_returns_count_of_deleted_rows(self, mock_db):
        """
        Executes a DELETE statement and returns the number of rows
        removed.
        """
        # Arrange
        mock_result = MagicMock()
        mock_result.rowcount = 4
        mock_db.execute.return_value = mock_result

        # Act
        result = password_reset_tokens_crud.delete_expired_password_reset_tokens(mock_db)

        # Assert
        assert result == 4
        mock_db.commit.assert_called_once()

    def test_returns_zero_when_no_expired_tokens(self, mock_db):
        """
        Returns 0 when there are no expired tokens to remove.
        """
        # Arrange
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        result = password_reset_tokens_crud.delete_expired_password_reset_tokens(mock_db)

        # Assert
        assert result == 0

    def test_query_filters_on_expires_at(self, mock_db):
        """
        Verifies the DELETE filters only by expires_at (expired rows).
        """
        # Arrange
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        # Act
        password_reset_tokens_crud.delete_expired_password_reset_tokens(mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        column_names = {c.left.name for c in criteria if hasattr(c, "left")}
        assert "expires_at" in column_names

    def test_db_error_raises_500(self, mock_db):
        """
        Raises HTTP 500 when a database error occurs.
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("db error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            password_reset_tokens_crud.delete_expired_password_reset_tokens(mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
