"""Tests for users_api_keys CRUD operations."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.auth.api_keys.crud as auth_api_keys_crud
import modules.auth.api_keys.models as users_api_keys_models
import modules.auth.api_keys.schema as users_api_keys_schema


class TestGetApiKeysByUserId:
    """
    Test suite for get_api_keys_by_user_id function.
    """

    def test_get_api_keys_by_user_id_returns_list(self, mock_db):
        """Test that a list of API keys is returned for a valid user."""
        # Arrange
        user_id = 1
        mock_key1 = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_key2 = MagicMock(spec=users_api_keys_models.UsersApiKeys)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_key1, mock_key2]
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_api_keys_crud.get_api_keys_by_user_id(user_id, mock_db)

        # Assert
        assert result == [mock_key1, mock_key2]
        mock_db.execute.assert_called_once()

    def test_get_api_keys_by_user_id_empty(self, mock_db):
        """Test that an empty list is returned when the user has no API keys."""
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_api_keys_crud.get_api_keys_by_user_id(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_api_keys_by_user_id_db_error(self, mock_db):
        """Test that a SQLAlchemyError raises an HTTP 500 error."""
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.get_api_keys_by_user_id(1, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetApiKeyById:
    """
    Test suite for get_api_key_by_id function.
    """

    def test_get_api_key_by_id_found(self, mock_db):
        """Test that the correct API key is returned when found."""
        # Arrange
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_api_keys_crud.get_api_key_by_id("some-uuid", 1, mock_db)

        # Assert
        assert result == mock_key

    def test_get_api_key_by_id_not_found(self, mock_db):
        """Test that None is returned when the API key does not exist."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_api_keys_crud.get_api_key_by_id("nonexistent-uuid", 1, mock_db)

        # Assert
        assert result is None

    def test_get_api_key_by_id_wrong_user_returns_none(self, mock_db):
        """Test that None is returned if the key belongs to a different user (ownership check)."""
        # Arrange — simulate no row matching both id AND user_id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_api_keys_crud.get_api_key_by_id("some-uuid", 999, mock_db)

        # Assert
        assert result is None

    def test_get_api_key_by_id_db_error(self, mock_db):
        """Test that a SQLAlchemyError raises an HTTP 500 error."""
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.get_api_key_by_id("some-uuid", 1, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetApiKeyByHash:
    """
    Test suite for get_api_key_by_hash function.
    """

    def test_get_api_key_by_hash_found(self, mock_db):
        """Test successful retrieval of an API key by its SHA-256 hash."""
        # Arrange
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_api_keys_crud.get_api_key_by_hash("a" * 64, mock_db)

        # Assert
        assert result == mock_key

    def test_get_api_key_by_hash_not_found(self, mock_db):
        """Test that None is returned when no key matches the hash."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = auth_api_keys_crud.get_api_key_by_hash("b" * 64, mock_db)

        # Assert
        assert result is None

    def test_get_api_key_by_hash_db_error(self, mock_db):
        """Test that a SQLAlchemyError raises an HTTP 500 error."""
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.get_api_key_by_hash("c" * 64, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateApiKey:
    """
    Test suite for create_api_key function.
    """

    def test_create_api_key_returns_tuple(self, mock_db):
        """Test that create_api_key returns a (ORM object, raw_key) tuple."""
        # Arrange
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        mock_orm_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)

        def fake_refresh(obj):
            # Simulate db.refresh populating the object
            pass

        mock_db.refresh.side_effect = fake_refresh

        # Act
        with patch(
            "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
            return_value=mock_orm_key,
        ):
            result = auth_api_keys_crud.create_api_key(1, data, mock_db)

        # Assert
        assert isinstance(result, tuple)
        assert len(result) == 2

    @patch(
        "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
        return_value=MagicMock(spec=users_api_keys_models.UsersApiKeys),
    )
    def test_create_api_key_calls_db_add_commit_refresh(self, _mock_model, mock_db):
        """Test that db.add, db.commit, and db.refresh are called during key creation."""
        # Arrange
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )

        # Act
        auth_api_keys_crud.create_api_key(1, data, mock_db)

        # Assert
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @patch(
        "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
        return_value=MagicMock(spec=users_api_keys_models.UsersApiKeys),
    )
    def test_create_api_key_raw_key_starts_with_prefix(self, _mock_model, mock_db):
        """Test that the returned raw key starts with 'endurain_'."""
        # Arrange
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )

        # Act
        _, raw_key = auth_api_keys_crud.create_api_key(1, data, mock_db)

        # Assert
        assert raw_key.startswith("endurain_")

    def test_create_api_key_key_prefix_is_correct_slice(self, mock_db):
        """Test that key_prefix passed to the UsersApiKeys constructor is chars 9-17 of the raw key."""
        # Arrange
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        captured_kwargs = {}
        mock_orm_obj = MagicMock(spec=users_api_keys_models.UsersApiKeys)

        def fake_constructor(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_orm_obj

        with patch(
            "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
            side_effect=fake_constructor,
        ):
            _, raw_key = auth_api_keys_crud.create_api_key(1, data, mock_db)

        # Assert — the key_prefix kwarg should be chars 9-17 of the raw key
        assert captured_kwargs["key_prefix"] == raw_key[9:17]

    def test_create_api_key_is_active_true(self, mock_db):
        """Test that newly created API keys have is_active=True."""
        # Arrange
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        captured_kwargs = {}
        mock_orm_obj = MagicMock(spec=users_api_keys_models.UsersApiKeys)

        def fake_constructor(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_orm_obj

        with patch(
            "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
            side_effect=fake_constructor,
        ):
            auth_api_keys_crud.create_api_key(1, data, mock_db)

        # Assert
        assert captured_kwargs["is_active"] is True

    def test_create_api_key_db_error(self, mock_db):
        """Test that a SQLAlchemyError raises an HTTP 500 error."""
        # Arrange
        data = users_api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        mock_db.add.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.create_api_key(1, data, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestUpdateLastUsed:
    """
    Test suite for update_last_used function.
    """

    def test_update_last_used_success(self, mock_db):
        """Test that last_used_at is updated and commit is called."""
        # Arrange
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result

        # Act
        auth_api_keys_crud.update_last_used("some-uuid", mock_db)

        # Assert
        assert mock_key.last_used_at is not None
        mock_db.commit.assert_called_once()

    def test_update_last_used_not_found_raises_404(self, mock_db):
        """Test that a 404 HTTPException is raised when the key is not found."""
        # Arrange
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_api_keys_crud.update_last_used("nonexistent-uuid", mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_update_last_used_db_error(self, mock_db):
        """Test that a SQLAlchemyError raises an HTTP 500 error."""
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        # Act & Assert
        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.update_last_used("some-uuid", mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestRevokeApiKey:
    """
    Test suite for revoke_api_key function.
    """

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_revoke_api_key_success(self, mock_get_by_id, mock_db):
        """Test that is_active is set to False and commit is called."""
        # Arrange
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_key.is_active = True
        mock_get_by_id.return_value = mock_key

        # Act
        auth_api_keys_crud.revoke_api_key("some-uuid", 1, mock_db)

        # Assert
        assert mock_key.is_active is False
        mock_db.commit.assert_called_once()

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_revoke_api_key_not_found_raises_404(self, mock_get_by_id, mock_db):
        """Test that a 404 is raised when the key does not exist or belong to the user."""
        # Arrange
        mock_get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_api_keys_crud.revoke_api_key("nonexistent-uuid", 1, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteApiKey:
    """
    Test suite for delete_api_key function.
    """

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_delete_api_key_success(self, mock_get_by_id, mock_db):
        """Test that db.delete and db.commit are called on a found key."""
        # Arrange
        mock_key = MagicMock(spec=users_api_keys_models.UsersApiKeys)
        mock_get_by_id.return_value = mock_key

        # Act
        auth_api_keys_crud.delete_api_key("some-uuid", 1, mock_db)

        # Assert
        mock_db.delete.assert_called_once_with(mock_key)
        mock_db.commit.assert_called_once()

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_delete_api_key_not_found_raises_404(self, mock_get_by_id, mock_db):
        """Test that a 404 is raised when the key does not exist or belong to the user."""
        # Arrange
        mock_get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            auth_api_keys_crud.delete_api_key("nonexistent-uuid", 1, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
