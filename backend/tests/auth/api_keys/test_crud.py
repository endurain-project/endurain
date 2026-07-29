"""Tests for auth.api_keys CRUD operations.

Canonical path tests — imports from auth.api_keys.* directly.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import core.exceptions as core_exceptions
import modules.auth.api_keys.crud as auth_api_keys_crud
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema


class TestGetApiKeysByUserId:
    """Test suite for get_api_keys_by_user_id."""

    def test_returns_list(self, mock_db):
        """Returns all API keys for a user."""
        user_id = 1
        mock_key1 = MagicMock(spec=api_keys_models.UsersApiKeys)
        mock_key2 = MagicMock(spec=api_keys_models.UsersApiKeys)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_key1, mock_key2]
        mock_db.execute.return_value = mock_result

        result = auth_api_keys_crud.get_api_keys_by_user_id(user_id, mock_db)

        assert result == [mock_key1, mock_key2]
        mock_db.execute.assert_called_once()

    def test_returns_empty_list_when_no_keys(self, mock_db):
        """Returns empty list when the user has no API keys."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = auth_api_keys_crud.get_api_keys_by_user_id(1, mock_db)

        assert result == []

    def test_db_error_raises_500(self, mock_db):
        """SQLAlchemy error raises HTTP 500."""
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.get_api_keys_by_user_id(1, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetApiKeyById:
    """Test suite for get_api_key_by_id."""

    def test_found_returns_key(self, mock_db):
        """Returns the key when it exists for the given user."""
        mock_key = MagicMock(spec=api_keys_models.UsersApiKeys)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result

        result = auth_api_keys_crud.get_api_key_by_id("some-uuid", 1, mock_db)

        assert result is mock_key

    def test_not_found_returns_none(self, mock_db):
        """Returns None when the key does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = auth_api_keys_crud.get_api_key_by_id("nonexistent-uuid", 1, mock_db)

        assert result is None

    def test_wrong_user_returns_none(self, mock_db):
        """Returns None when the key exists but belongs to a different user."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = auth_api_keys_crud.get_api_key_by_id("some-uuid", 999, mock_db)

        assert result is None

    def test_db_error_raises_500(self, mock_db):
        """SQLAlchemy error raises HTTP 500."""
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.get_api_key_by_id("some-uuid", 1, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetApiKeyByHash:
    """Test suite for get_api_key_by_hash."""

    def test_found_returns_key(self, mock_db):
        """Returns the key matching the SHA-256 hash."""
        mock_key = MagicMock(spec=api_keys_models.UsersApiKeys)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result

        result = auth_api_keys_crud.get_api_key_by_hash("a" * 64, mock_db)

        assert result is mock_key

    def test_not_found_returns_none(self, mock_db):
        """Returns None when no key matches the hash."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = auth_api_keys_crud.get_api_key_by_hash("b" * 64, mock_db)

        assert result is None

    def test_db_error_raises_500(self, mock_db):
        """SQLAlchemy error raises HTTP 500."""
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.get_api_key_by_hash("c" * 64, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateApiKey:
    """Test suite for create_api_key."""

    def test_returns_orm_and_raw_key_tuple(self, mock_db):
        """Returns a (ORM object, raw_key) tuple."""
        data = api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        mock_orm_key = MagicMock(spec=api_keys_models.UsersApiKeys)

        with patch(
            "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
            return_value=mock_orm_key,
        ):
            result = auth_api_keys_crud.create_api_key(1, data, mock_db)

        assert isinstance(result, tuple)
        assert len(result) == 2

    @patch(
        "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
        return_value=MagicMock(spec=api_keys_models.UsersApiKeys),
    )
    def test_calls_db_add_commit_refresh(self, _mock_model, mock_db):
        """db.add, db.commit, and db.refresh are all called."""
        data = api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )

        auth_api_keys_crud.create_api_key(1, data, mock_db)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @patch(
        "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
        return_value=MagicMock(spec=api_keys_models.UsersApiKeys),
    )
    def test_raw_key_starts_with_endurain_prefix(self, _mock_model, mock_db):
        """The raw key returned always starts with 'endurain_'."""
        data = api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )

        _, raw_key = auth_api_keys_crud.create_api_key(1, data, mock_db)

        assert raw_key.startswith("endurain_")

    def test_key_prefix_is_correct_slice(self, mock_db):
        """The key_prefix stored is chars 9-17 of the raw key."""
        data = api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        captured_kwargs: dict = {}
        mock_orm_obj = MagicMock(spec=api_keys_models.UsersApiKeys)

        def fake_constructor(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_orm_obj

        with patch(
            "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
            side_effect=fake_constructor,
        ):
            _, raw_key = auth_api_keys_crud.create_api_key(1, data, mock_db)

        assert captured_kwargs["key_prefix"] == raw_key[9:17]

    def test_new_key_is_active(self, mock_db):
        """Newly created API keys have is_active=True."""
        data = api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        captured_kwargs: dict = {}
        mock_orm_obj = MagicMock(spec=api_keys_models.UsersApiKeys)

        def fake_constructor(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_orm_obj

        with patch(
            "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
            side_effect=fake_constructor,
        ):
            auth_api_keys_crud.create_api_key(1, data, mock_db)

        assert captured_kwargs["is_active"] is True

    def test_hash_stored_not_raw_key(self, mock_db):
        """The key_hash stored is the SHA-256 hex digest, not the raw key."""
        import hashlib

        data = api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        captured_kwargs: dict = {}
        mock_orm_obj = MagicMock(spec=api_keys_models.UsersApiKeys)

        def fake_constructor(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_orm_obj

        with patch(
            "modules.auth.api_keys.crud.api_keys_models.UsersApiKeys",
            side_effect=fake_constructor,
        ):
            _, raw_key = auth_api_keys_crud.create_api_key(1, data, mock_db)

        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        assert captured_kwargs["key_hash"] == expected_hash

    def test_db_error_raises_500(self, mock_db):
        """SQLAlchemy error on db.add raises HTTP 500."""
        data = api_keys_schema.UsersApiKeyCreate(
            name="Test Key",
            scopes=["activities:upload"],
        )
        mock_db.add.side_effect = SQLAlchemyError("DB error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.create_api_key(1, data, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestUpdateLastUsed:
    """Test suite for update_last_used."""

    def test_success_updates_timestamp_and_commits(self, mock_db):
        """last_used_at is updated and db.commit is called."""
        mock_key = MagicMock(spec=api_keys_models.UsersApiKeys)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_key
        mock_db.execute.return_value = mock_result

        auth_api_keys_crud.update_last_used("some-uuid", mock_db)

        assert mock_key.last_used_at is not None
        mock_db.commit.assert_called_once()

    def test_not_found_raises_404(self, mock_db):
        """Raises 404 when the API key UUID is unknown."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            auth_api_keys_crud.update_last_used("nonexistent-uuid", mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND

    def test_db_error_raises_500(self, mock_db):
        """SQLAlchemy error raises HTTP 500."""
        mock_db.execute.side_effect = SQLAlchemyError("DB error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            auth_api_keys_crud.update_last_used("some-uuid", mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestRevokeApiKey:
    """Test suite for revoke_api_key."""

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_success_sets_is_active_false(self, mock_get_by_id, mock_db):
        """is_active is set to False and commit is called."""
        mock_key = MagicMock(spec=api_keys_models.UsersApiKeys)
        mock_key.is_active = True
        mock_get_by_id.return_value = mock_key

        auth_api_keys_crud.revoke_api_key("some-uuid", 1, mock_db)

        assert mock_key.is_active is False
        mock_db.commit.assert_called_once()

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_not_found_raises_404(self, mock_get_by_id, mock_db):
        """Raises 404 when the key is not found for the user."""
        mock_get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            auth_api_keys_crud.revoke_api_key("nonexistent-uuid", 1, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteApiKey:
    """Test suite for delete_api_key."""

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_success_deletes_and_commits(self, mock_get_by_id, mock_db):
        """db.delete and db.commit are called for a found key."""
        mock_key = MagicMock(spec=api_keys_models.UsersApiKeys)
        mock_get_by_id.return_value = mock_key

        auth_api_keys_crud.delete_api_key("some-uuid", 1, mock_db)

        mock_db.delete.assert_called_once_with(mock_key)
        mock_db.commit.assert_called_once()

    @patch("modules.auth.api_keys.crud.get_api_key_by_id")
    def test_not_found_raises_404(self, mock_get_by_id, mock_db):
        """Raises 404 when the key is not found for the user."""
        mock_get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            auth_api_keys_crud.delete_api_key("nonexistent-uuid", 1, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
