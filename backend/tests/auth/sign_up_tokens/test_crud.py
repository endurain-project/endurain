"""Tests for sign-up token CRUD operations."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy.sql import operators

import modules.auth.sign_up_tokens.crud as sign_up_tokens_crud
import modules.auth.sign_up_tokens.schema as sign_up_tokens_schema


class TestGetSignUpTokenByHash:
    """Test suite for get_sign_up_token_by_hash function."""

    def test_get_sign_up_token_by_hash_found_returns_token(self, mock_db):
        """Valid hash returns the matching token."""
        # Arrange
        mock_token = object()
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_token

        # Act
        result = sign_up_tokens_crud.get_sign_up_token_by_hash("abc123hash", mock_db)

        # Assert
        assert result is mock_token

    def test_get_sign_up_token_by_hash_not_found_returns_none(self, mock_db):
        """None returned when no matching token exists."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = sign_up_tokens_crud.get_sign_up_token_by_hash("nonexistenthash", mock_db)

        # Assert
        assert result is None

    def test_get_sign_up_token_by_hash_query_filters_hash(self, mock_db):
        """SELECT WHERE clause includes token_hash == hash."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        sign_up_tokens_crud.get_sign_up_token_by_hash("some-hash", mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        assert any(criterion.left.name == "token_hash" and criterion.operator is operators.eq for criterion in criteria)

    def test_get_sign_up_token_by_hash_query_filters_used(self, mock_db):
        """SELECT WHERE clause filters unused tokens."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        sign_up_tokens_crud.get_sign_up_token_by_hash("some-hash", mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        assert any(criterion.left.name == "used" and criterion.operator is operators.is_ for criterion in criteria)

    def test_get_sign_up_token_by_hash_query_filters_expiry(self, mock_db):
        """SELECT WHERE clause filters unexpired tokens."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        sign_up_tokens_crud.get_sign_up_token_by_hash("some-hash", mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        assert any(criterion.left.name == "expires_at" and criterion.operator is operators.gt for criterion in criteria)


class TestCreateSignUpToken:
    """Test suite for create_sign_up_token CRUD function."""

    @patch("modules.auth.sign_up_tokens.crud.sign_up_tokens_models.SignUpToken")
    def test_create_sign_up_token_persists_and_returns_token(self, mock_model_class, mock_db):
        """Token is added, committed, refreshed, and returned."""
        # Arrange
        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance
        now = datetime.now(UTC)
        token_schema = sign_up_tokens_schema.SignUpToken(
            id="token-uuid-1234",
            user_id=7,
            token_hash="hashvalue",
            created_at=now,
            expires_at=now,
            used=False,
        )

        # Act
        result = sign_up_tokens_crud.create_sign_up_token(token_schema, mock_db)

        # Assert
        mock_db.add.assert_called_once_with(mock_instance)
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_instance)
        assert result is mock_instance


class TestMarkSignUpTokenUsed:
    """Test suite for mark_sign_up_token_used function."""

    def test_mark_sign_up_token_used_sets_used_true(self, mock_db):
        """Existing token is marked used and returned."""
        # Arrange
        mock_token = MagicMock()
        mock_token.used = False
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_token

        # Act
        result = sign_up_tokens_crud.mark_sign_up_token_used("some-token-id", mock_db)

        # Assert
        assert mock_token.used is True
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_token)
        assert result is mock_token

    def test_mark_sign_up_token_used_not_found_returns_none(self, mock_db):
        """None returned when token id does not exist."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = sign_up_tokens_crud.mark_sign_up_token_used("missing-id", mock_db)

        # Assert
        assert result is None
        mock_db.commit.assert_not_called()
        mock_db.refresh.assert_not_called()

    def test_mark_sign_up_token_used_query_filters_by_id(self, mock_db):
        """SELECT WHERE clause filters by token id."""
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        sign_up_tokens_crud.mark_sign_up_token_used("token-id-abc", mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        assert any(criterion.left.name == "id" and criterion.operator is operators.eq for criterion in criteria)


class TestDeleteExpiredSignUpTokens:
    """Test suite for delete_expired_sign_up_tokens function."""

    def test_delete_expired_sign_up_tokens_returns_rowcount(self, mock_db):
        """Number of deleted rows is returned."""
        # Arrange
        mock_db.execute.return_value.rowcount = 5

        # Act
        result = sign_up_tokens_crud.delete_expired_sign_up_tokens(mock_db)

        # Assert
        assert result == 5
        mock_db.commit.assert_called_once()

    def test_delete_expired_sign_up_tokens_zero_returns_zero(self, mock_db):
        """Zero returned when no expired tokens exist."""
        # Arrange
        mock_db.execute.return_value.rowcount = 0

        # Act
        result = sign_up_tokens_crud.delete_expired_sign_up_tokens(mock_db)

        # Assert
        assert result == 0
        mock_db.commit.assert_called_once()

    def test_delete_expired_sign_up_tokens_query_filters_expiry(self, mock_db):
        """DELETE WHERE clause filters by expires_at < now."""
        # Arrange
        mock_db.execute.return_value.rowcount = 0

        # Act
        sign_up_tokens_crud.delete_expired_sign_up_tokens(mock_db)

        # Assert
        stmt = mock_db.execute.call_args.args[0]
        criteria = stmt._where_criteria
        assert any(criterion.left.name == "expires_at" and criterion.operator is operators.lt for criterion in criteria)
