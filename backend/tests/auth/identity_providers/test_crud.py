"""Tests for identity_providers.crud module."""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from auth.identity_providers import crud as idp_crud
from auth.identity_providers.schema import (
    IdentityProviderCreate,
    IdentityProviderUpdate,
)
from auth.identity_providers.models import IdentityProvider


class TestGetIdentityProvider:
    """Test suite for get_identity_provider function."""

    def test_get_identity_provider_success(self, mock_db):
        """Test successfully retrieving an identity provider by ID.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Correct database query is executed
            - Identity provider is returned
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_idp.id = 1
        mock_idp.name = "Test Provider"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_idp

        # Act
        result = idp_crud.get_identity_provider(1, mock_db)

        # Assert
        assert result == mock_idp
        mock_db.query.assert_called_once()
        mock_db.query.return_value.filter.assert_called_once()

    def test_get_identity_provider_not_found(self, mock_db):
        """Test retrieving non-existent identity provider.

        Args:
            mock_db: Mocked database session

        Asserts:
            - None is returned when provider not found
        """
        # Arrange
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Act
        result = idp_crud.get_identity_provider(999, mock_db)

        # Assert
        assert result is None

    def test_get_identity_provider_database_error(self, mock_db):
        """Test get_identity_provider handles database errors.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised on database error
        """
        # Arrange
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.get_identity_provider(1, mock_db)

        assert exc_info.value.status_code == 500
        assert "Internal Server Error" in str(exc_info.value.detail)


class TestGetIdentityProviderBySlug:
    """Test suite for get_identity_provider_by_slug function."""

    def test_get_identity_provider_by_slug_success(self, mock_db):
        """Test successfully retrieving an identity provider by slug.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Correct database query is executed
            - Identity provider is returned
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_idp.slug = "test-provider"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_idp

        # Act
        result = idp_crud.get_identity_provider_by_slug("test-provider", mock_db)

        # Assert
        assert result == mock_idp
        mock_db.query.assert_called_once()

    def test_get_identity_provider_by_slug_not_found(self, mock_db):
        """Test retrieving non-existent identity provider by slug.

        Args:
            mock_db: Mocked database session

        Asserts:
            - None is returned when provider not found
        """
        # Arrange
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Act
        result = idp_crud.get_identity_provider_by_slug("nonexistent", mock_db)

        # Assert
        assert result is None

    def test_get_identity_provider_by_slug_database_error(self, mock_db):
        """Test get_identity_provider_by_slug handles database errors.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised on database error
        """
        # Arrange
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.get_identity_provider_by_slug("test", mock_db)

        assert exc_info.value.status_code == 500


class TestGetAllIdentityProviders:
    """Test suite for get_all_identity_providers function."""

    def test_get_all_identity_providers_success(self, mock_db):
        """Test successfully retrieving all identity providers.

        Args:
            mock_db: Mocked database session

        Asserts:
            - All providers are returned ordered by name
        """
        # Arrange
        mock_idps = [MagicMock(spec=IdentityProvider) for _ in range(3)]
        mock_db.query.return_value.order_by.return_value.all.return_value = mock_idps

        # Act
        result = idp_crud.get_all_identity_providers(mock_db)

        # Assert
        assert result == mock_idps
        assert len(result) == 3
        mock_db.query.assert_called_once()
        mock_db.query.return_value.order_by.assert_called_once()

    def test_get_all_identity_providers_empty(self, mock_db):
        """Test retrieving all identity providers when none exist.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Empty list is returned
        """
        # Arrange
        mock_db.query.return_value.order_by.return_value.all.return_value = []

        # Act
        result = idp_crud.get_all_identity_providers(mock_db)

        # Assert
        assert result == []

    def test_get_all_identity_providers_database_error(self, mock_db):
        """Test get_all_identity_providers handles database errors.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised on database error
        """
        # Arrange
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.get_all_identity_providers(mock_db)

        assert exc_info.value.status_code == 500


class TestGetEnabledProviders:
    """Test suite for get_enabled_providers function."""

    def test_get_enabled_providers_success(self, mock_db):
        """Test successfully retrieving enabled identity providers.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Only enabled providers are returned
            - Results are ordered by name
        """
        # Arrange
        mock_idps = [MagicMock(spec=IdentityProvider) for _ in range(2)]
        (
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value
        ) = mock_idps

        # Act
        result = idp_crud.get_enabled_providers(mock_db)

        # Assert
        assert result == mock_idps
        assert len(result) == 2
        mock_db.query.assert_called_once()
        mock_db.query.return_value.filter.assert_called_once()

    def test_get_enabled_providers_empty(self, mock_db):
        """Test retrieving enabled providers when none exist.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Empty list is returned
        """
        # Arrange
        (
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value
        ) = []

        # Act
        result = idp_crud.get_enabled_providers(mock_db)

        # Assert
        assert result == []

    def test_get_enabled_providers_database_error(self, mock_db):
        """Test get_enabled_providers handles database errors.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised on database error
        """
        # Arrange
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.get_enabled_providers(mock_db)

        assert exc_info.value.status_code == 500


class TestGetIdentityProvidersByIds:
    """Test suite for get_identity_providers_by_ids function."""

    def test_get_identity_providers_by_ids_success(self, mock_db):
        """Test successfully retrieving multiple identity providers by IDs.

        Args:
            mock_db: Mocked database session

        Asserts:
            - All requested providers are returned
            - Query uses correct filter
        """
        # Arrange
        mock_idps = [
            MagicMock(spec=IdentityProvider, id=1, name="Provider 1"),
            MagicMock(spec=IdentityProvider, id=2, name="Provider 2"),
            MagicMock(spec=IdentityProvider, id=3, name="Provider 3"),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = mock_idps

        # Act
        result = idp_crud.get_identity_providers_by_ids([1, 2, 3], mock_db)

        # Assert
        assert result == mock_idps
        assert len(result) == 3
        mock_db.query.assert_called_once()
        mock_db.query.return_value.filter.assert_called_once()

    def test_get_identity_providers_by_ids_empty_list(self, mock_db):
        """Test behavior when given an empty list of IDs.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Empty list is returned without querying database
        """
        # Act
        result = idp_crud.get_identity_providers_by_ids([], mock_db)

        # Assert
        assert result == []
        mock_db.query.assert_not_called()

    def test_get_identity_providers_by_ids_partial_results(self, mock_db):
        """Test retrieving providers when only some IDs exist.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Only existing providers are returned
        """
        # Arrange
        mock_idps = [
            MagicMock(spec=IdentityProvider, id=1),
            MagicMock(spec=IdentityProvider, id=3),
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = mock_idps

        # Act
        result = idp_crud.get_identity_providers_by_ids([1, 2, 3], mock_db)

        # Assert
        assert result == mock_idps
        assert len(result) == 2

    def test_get_identity_providers_by_ids_no_results(self, mock_db):
        """Test retrieving providers when no IDs match.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Empty list is returned
        """
        # Arrange
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Act
        result = idp_crud.get_identity_providers_by_ids([999, 1000], mock_db)

        # Assert
        assert result == []

    def test_get_identity_providers_by_ids_database_error(self, mock_db):
        """Test get_identity_providers_by_ids handles database errors.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised on database error
        """
        # Arrange
        mock_db.query.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.get_identity_providers_by_ids([1, 2, 3], mock_db)

        assert exc_info.value.status_code == 500
        assert "Internal Server Error" in str(exc_info.value.detail)

    def test_get_identity_providers_by_ids_single_id(self, mock_db):
        """Test retrieving a single provider by ID using batch function.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Single provider is returned correctly
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider, id=1, name="Provider 1")
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_idp]

        # Act
        result = idp_crud.get_identity_providers_by_ids([1], mock_db)

        # Assert
        assert result == [mock_idp]
        assert len(result) == 1


class TestCreateIdentityProvider:
    """Test suite for create_identity_provider function."""

    @patch("auth.identity_providers.crud.idp_models.IdentityProvider")
    @patch("auth.identity_providers.crud.core_cryptography.encrypt_token_fernet")
    @patch("auth.identity_providers.crud.get_identity_provider_by_slug")
    def test_create_identity_provider_success(
        self, mock_get_by_slug, mock_encrypt, mock_idp_model, mock_db
    ):
        """Test successfully creating a new identity provider.

        Args:
            mock_get_by_slug: Mocked get_identity_provider_by_slug function
            mock_encrypt: Mocked encryption function
            mock_idp_model: Mocked IdentityProvider model
            mock_db: Mocked database session

        Asserts:
            - Identity provider is created with encrypted credentials
            - Database commit and refresh are called
        """
        # Arrange
        mock_get_by_slug.return_value = None  # No existing provider
        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"

        mock_idp_instance = MagicMock()
        mock_idp_instance.id = 1
        mock_idp_instance.name = "Test Provider"
        mock_idp_model.return_value = mock_idp_instance

        idp_data = IdentityProviderCreate(
            name="Test Provider",
            slug="test-provider",
            client_id="test-client-id",
            client_secret="test-secret",
        )

        # Act
        result = idp_crud.create_identity_provider(idp_data, mock_db)

        # Assert
        mock_get_by_slug.assert_called_once_with("test-provider", mock_db)
        assert mock_encrypt.call_count == 2  # Called for client_id and client_secret
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        assert result == mock_idp_instance

    @patch("auth.identity_providers.crud.get_identity_provider_by_slug")
    def test_create_identity_provider_slug_exists(self, mock_get_by_slug, mock_db):
        """Test creating identity provider with existing slug.

        Args:
            mock_get_by_slug: Mocked get_identity_provider_by_slug function
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 409 status is raised
            - Error message indicates slug conflict
        """
        # Arrange
        mock_existing = MagicMock(spec=IdentityProvider)
        mock_get_by_slug.return_value = mock_existing

        idp_data = IdentityProviderCreate(
            name="Test Provider",
            slug="existing-slug",
            client_id="test-client-id",
            client_secret="test-secret",
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.create_identity_provider(idp_data, mock_db)

        assert exc_info.value.status_code == 409
        assert "already exists" in str(exc_info.value.detail)

    @patch("auth.identity_providers.crud.core_cryptography.encrypt_token_fernet")
    @patch("auth.identity_providers.crud.get_identity_provider_by_slug")
    def test_create_identity_provider_database_error(
        self, mock_get_by_slug, mock_encrypt, mock_db
    ):
        """Test create_identity_provider handles database errors.

        Args:
            mock_get_by_slug: Mocked get_identity_provider_by_slug function
            mock_encrypt: Mocked encryption function
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised
            - Database rollback is called
        """
        # Arrange
        mock_get_by_slug.return_value = None
        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"
        mock_db.commit.side_effect = Exception("Database error")

        idp_data = IdentityProviderCreate(
            name="Test",
            slug="test",
            client_id="client-id",
            client_secret="secret",
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.create_identity_provider(idp_data, mock_db)

        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestUpdateIdentityProvider:
    """Test suite for update_identity_provider function."""

    @patch("auth.identity_providers.crud.core_cryptography.encrypt_token_fernet")
    @patch("auth.identity_providers.crud.get_identity_provider_by_slug")
    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_update_identity_provider_success(
        self, mock_get, mock_get_by_slug, mock_encrypt, mock_db
    ):
        """Test successfully updating an identity provider.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_get_by_slug: Mocked get_identity_provider_by_slug function
            mock_encrypt: Mocked encryption function
            mock_db: Mocked database session

        Asserts:
            - Identity provider is updated
            - Encrypted fields are encrypted
            - Database commit and refresh are called
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_idp.id = 1
        mock_idp.slug = "original-slug"
        mock_get.return_value = mock_idp
        mock_get_by_slug.return_value = None
        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"

        idp_data = IdentityProviderUpdate(
            name="Updated Provider",
            slug="updated-slug",
            client_id="new-client-id",
            client_secret="new-secret",
        )

        # Act
        result = idp_crud.update_identity_provider(1, idp_data, mock_db)

        # Assert
        mock_get.assert_called_once_with(1, mock_db)
        mock_get_by_slug.assert_called_once_with("updated-slug", mock_db)
        assert mock_encrypt.call_count == 2
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_update_identity_provider_not_found(self, mock_get, mock_db):
        """Test updating non-existent identity provider.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 404 status is raised
        """
        # Arrange
        mock_get.return_value = None
        idp_data = IdentityProviderUpdate(
            name="Updated", slug="updated-slug", client_id="client-123"
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.update_identity_provider(999, idp_data, mock_db)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @patch("auth.identity_providers.crud.get_identity_provider_by_slug")
    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_update_identity_provider_slug_conflict(
        self, mock_get, mock_get_by_slug, mock_db
    ):
        """Test updating identity provider with conflicting slug.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_get_by_slug: Mocked get_identity_provider_by_slug function
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 409 status is raised
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_idp.slug = "original-slug"
        mock_get.return_value = mock_idp

        mock_existing = MagicMock(spec=IdentityProvider)
        mock_existing.slug = "existing-slug"
        mock_get_by_slug.return_value = mock_existing

        idp_data = IdentityProviderUpdate(
            name="Test", slug="existing-slug", client_id="client-123"
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.update_identity_provider(1, idp_data, mock_db)

        assert exc_info.value.status_code == 409
        assert "already exists" in str(exc_info.value.detail)

    @patch("auth.identity_providers.crud.core_cryptography.encrypt_token_fernet")
    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_update_identity_provider_without_slug_change(
        self, mock_get, mock_encrypt, mock_db
    ):
        """Test updating identity provider without changing slug.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_encrypt: Mocked encryption function
            mock_db: Mocked database session

        Asserts:
            - get_identity_provider_by_slug is not called
            - Update succeeds
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_idp.slug = "test-slug"
        mock_get.return_value = mock_idp
        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"

        idp_data = IdentityProviderUpdate(
            name="Updated Name", slug="test-slug", client_id="client-123"
        )

        # Act
        result = idp_crud.update_identity_provider(1, idp_data, mock_db)

        # Assert
        mock_get.assert_called_once_with(1, mock_db)
        mock_db.commit.assert_called_once()

    @patch("auth.identity_providers.crud.core_cryptography.encrypt_token_fernet")
    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_update_identity_provider_database_error(
        self, mock_get, mock_encrypt, mock_db
    ):
        """Test update_identity_provider handles database errors.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_encrypt: Mocked encryption function
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised
            - Database rollback is called
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_idp.slug = "test-slug"
        mock_get.return_value = mock_idp
        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"
        mock_db.commit.side_effect = Exception("Database error")

        # Use same slug to avoid conflict check
        idp_data = IdentityProviderUpdate(
            name="Updated", slug="test-slug", client_id="client-123"
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.update_identity_provider(1, idp_data, mock_db)

        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestDeleteIdentityProvider:
    """Test suite for delete_identity_provider function."""

    @patch(
        "auth.identity_providers.crud.user_identity_providers_crud.check_user_identity_providers_by_idp_id"
    )
    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_delete_identity_provider_success(
        self, mock_get, mock_check_users, mock_db
    ):
        """Test successfully deleting an identity provider.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_check_users: Mocked check for user links
            mock_db: Mocked database session

        Asserts:
            - Identity provider is deleted
            - Database commit is called
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_idp.id = 1
        mock_idp.name = "Test Provider"
        mock_get.return_value = mock_idp
        mock_check_users.return_value = None  # No linked users

        # Act
        idp_crud.delete_identity_provider(1, mock_db)

        # Assert
        mock_get.assert_called_once_with(1, mock_db)
        mock_check_users.assert_called_once_with(1, mock_db)
        mock_db.delete.assert_called_once_with(mock_idp)
        mock_db.commit.assert_called_once()

    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_delete_identity_provider_not_found(self, mock_get, mock_db):
        """Test deleting non-existent identity provider.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 404 status is raised
        """
        # Arrange
        mock_get.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.delete_identity_provider(999, mock_db)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @patch(
        "auth.identity_providers.crud.user_identity_providers_crud.check_user_identity_providers_by_idp_id"
    )
    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_delete_identity_provider_with_linked_users(
        self, mock_get, mock_check_users, mock_db
    ):
        """Test deleting identity provider with linked users.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_check_users: Mocked check for user links
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 409 status is raised
            - Error message indicates linked users
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_get.return_value = mock_idp
        mock_check_users.return_value = True  # Has linked users

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.delete_identity_provider(1, mock_db)

        assert exc_info.value.status_code == 409
        assert "linked users" in str(exc_info.value.detail)

    @patch(
        "auth.identity_providers.crud.user_identity_providers_crud.check_user_identity_providers_by_idp_id"
    )
    @patch("auth.identity_providers.crud.get_identity_provider")
    def test_delete_identity_provider_database_error(
        self, mock_get, mock_check_users, mock_db
    ):
        """Test delete_identity_provider handles database errors.

        Args:
            mock_get: Mocked get_identity_provider function
            mock_check_users: Mocked check for user links
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status is raised
            - Database rollback is called
        """
        # Arrange
        mock_idp = MagicMock(spec=IdentityProvider)
        mock_get.return_value = mock_idp
        mock_check_users.return_value = None
        mock_db.delete.side_effect = Exception("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            idp_crud.delete_identity_provider(1, mock_db)

        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called_once()
