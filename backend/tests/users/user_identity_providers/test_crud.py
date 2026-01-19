"""Tests for user_identity_providers.crud module."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from users.users_identity_providers import crud as user_idp_crud
from users.users_identity_providers.models import UsersIdentityProvider


class TestCheckUserIdentityProvidersByIdpId:
    """Test suite for check_user_identity_providers_by_idp_id function."""

    def test_check_user_identity_providers_by_idp_id_success_found(self, mock_db):
        """Test checking for identity providers with existing links.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns True when at least one user is linked
        """
        # Arrange
        mock_db.execute.return_value.scalar.return_value = True

        # Act
        result = user_idp_crud.check_user_identity_providers_by_idp_id(1, mock_db)

        # Assert
        assert result is True
        mock_db.execute.assert_called_once()

    def test_check_user_identity_providers_by_idp_id_success_not_found(self, mock_db):
        """Test checking for identity providers with no links.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns False when no users are linked
        """
        # Arrange
        mock_db.execute.return_value.scalar.return_value = None

        # Act
        result = user_idp_crud.check_user_identity_providers_by_idp_id(1, mock_db)

        # Assert
        assert result is False

    def test_check_user_identity_providers_by_idp_id_database_error(self, mock_db):
        """Test database error handling.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status on database error
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_idp_crud.check_user_identity_providers_by_idp_id(1, mock_db)

        assert exc_info.value.status_code == 500


class TestGetUserIdentityProvidersByUserId:
    """Test suite for get_user_identity_providers_by_user_id function."""

    def test_get_user_identity_providers_by_user_id_success(self, mock_db):
        """Test retrieving all identity provider links for a user.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns list of UsersIdentityProvider objects
            - Database query is executed correctly
        """
        # Arrange
        mock_link1 = MagicMock(spec=UsersIdentityProvider)
        mock_link1.id = 1
        mock_link1.user_id = 1
        mock_link1.idp_id = 1

        mock_link2 = MagicMock(spec=UsersIdentityProvider)
        mock_link2.id = 2
        mock_link2.user_id = 1
        mock_link2.idp_id = 2

        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            mock_link1,
            mock_link2,
        ]

        # Act
        result = user_idp_crud.get_user_identity_providers_by_user_id(1, mock_db)

        # Assert
        assert len(result) == 2
        assert result[0].idp_id == 1
        assert result[1].idp_id == 2
        mock_db.execute.assert_called_once()

    def test_get_user_identity_providers_by_user_id_empty_list(self, mock_db):
        """Test retrieving links when user has no IdP links.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns empty list when no links exist
        """
        # Arrange
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        # Act
        result = user_idp_crud.get_user_identity_providers_by_user_id(1, mock_db)

        # Assert
        assert result == []

    def test_get_user_identity_providers_by_user_id_database_error(self, mock_db):
        """Test database error handling.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status on database error
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_idp_crud.get_user_identity_providers_by_user_id(1, mock_db)

        assert exc_info.value.status_code == 500


class TestGetUserIdentityProviderByUserIdAndIdpId:
    """Test suite for get_user_identity_provider_by_user_id_and_idp_id function."""

    def test_get_user_identity_provider_by_user_id_and_idp_id_success(self, mock_db):
        """Test retrieving a specific identity provider link for a user.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns UsersIdentityProvider object when found
            - Database query uses correct filters
        """
        # Arrange
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1
        mock_link.user_id = 1
        mock_link.idp_id = 1
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_link

        # Act
        result = user_idp_crud.get_user_identity_provider_by_user_id_and_idp_id(
            1, 1, mock_db
        )

        # Assert
        assert result == mock_link
        mock_db.execute.assert_called_once()

    def test_get_user_identity_provider_by_user_id_and_idp_id_not_found(self, mock_db):
        """Test retrieving non-existent identity provider link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when link not found
        """
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = user_idp_crud.get_user_identity_provider_by_user_id_and_idp_id(
            1, 999, mock_db
        )

        # Assert
        assert result is None

    def test_get_user_identity_provider_by_user_id_and_idp_id_database_error(
        self, mock_db
    ):
        """Test database error handling.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status on database error
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_idp_crud.get_user_identity_provider_by_user_id_and_idp_id(
                1, 1, mock_db
            )

        assert exc_info.value.status_code == 500


class TestGetUserIdentityProviderBySubjectAndIdpId:
    """Test suite for get_user_identity_provider_by_subject_and_idp_id function."""

    def test_get_user_identity_provider_by_subject_and_idp_id_success(self, mock_db):
        """Test retrieving identity provider link by subject.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns UsersIdentityProvider object when found
            - Database query uses subject and IdP ID filters
        """
        # Arrange
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1
        mock_link.user_id = 1
        mock_link.idp_id = 1
        mock_link.idp_subject = "user123@provider.com"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_link

        # Act
        result = user_idp_crud.get_user_identity_provider_by_subject_and_idp_id(
            1, "user123@provider.com", mock_db
        )

        # Assert
        assert result == mock_link
        assert result.idp_subject == "user123@provider.com"
        mock_db.execute.assert_called_once()

    def test_get_user_identity_provider_by_subject_and_idp_id_not_found(self, mock_db):
        """Test retrieving non-existent link by subject.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when link not found
        """
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = user_idp_crud.get_user_identity_provider_by_subject_and_idp_id(
            1, "nonexistent@provider.com", mock_db
        )

        # Assert
        assert result is None

    def test_get_user_identity_provider_by_subject_and_idp_id_database_error(
        self, mock_db
    ):
        """Test database error handling.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status on database error
        """
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_idp_crud.get_user_identity_provider_by_subject_and_idp_id(
                1, "user@provider.com", mock_db
            )

        assert exc_info.value.status_code == 500


class TestCreateUserIdentityProvider:
    """Test suite for create_user_identity_provider function."""

    def test_create_user_identity_provider_success(self, mock_db):
        """Test creating a new user identity provider link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - New link is created with correct attributes
            - Database add and commit are called
            - Link object is returned
        """
        # Arrange
        now = datetime.now(timezone.utc)
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1
        mock_link.user_id = 1
        mock_link.idp_id = 1
        mock_link.idp_subject = "user123"
        mock_link.last_login = now

        # Mock the add, commit, and refresh methods
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        # Patch the UsersIdentityProvider constructor
        with patch(
            "users.users_identity_providers.crud.user_idp_models.UsersIdentityProvider"
        ) as mock_constructor:
            mock_constructor.return_value = mock_link

            # Act
            result = user_idp_crud.create_user_identity_provider(
                1, 1, "user123", mock_db
            )

        # Assert
        assert result == mock_link
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_create_user_identity_provider_database_error(self, mock_db):
        """Test database error during link creation.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status on database error
            - Rollback is called
        """
        # Arrange
        mock_db.add.side_effect = SQLAlchemyError("Database error")
        mock_db.rollback = MagicMock()

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            user_idp_crud.create_user_identity_provider(1, 1, "user123", mock_db)

        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestUpdateUserIdentityProviderLastLogin:
    """Test suite for update_user_identity_provider_last_login function."""

    def test_update_user_identity_provider_last_login_success(self, mock_db):
        """Test updating last login timestamp.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Last login timestamp is updated
            - Database commit and refresh are called
        """
        # Arrange
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1
        mock_link.user_id = 1
        mock_link.idp_id = 1

        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = mock_link
            mock_db.commit = MagicMock()
            mock_db.refresh = MagicMock()

            # Act
            result = user_idp_crud.update_user_identity_provider_last_login(
                1, 1, mock_db
            )

        # Assert
        assert result == mock_link
        assert mock_link.last_login is not None
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_update_user_identity_provider_last_login_not_found(self, mock_db):
        """Test updating last login for non-existent link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when link not found
            - No database operations performed
        """
        # Arrange
        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = None

            # Act
            result = user_idp_crud.update_user_identity_provider_last_login(
                1, 1, mock_db
            )

        # Assert
        assert result is None
        mock_db.commit.assert_not_called()


class TestStoreUserIdentityProviderTokens:
    """Test suite for store_user_identity_provider_tokens function."""

    def test_store_user_identity_provider_tokens_success(self, mock_db):
        """Test storing encrypted tokens for user IdP link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Tokens are stored in the link
            - Timestamp is updated
            - Database commit and refresh are called
        """
        # Arrange
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1
        mock_link.user_id = 1
        mock_link.idp_id = 1

        expires_at = datetime.now(timezone.utc)
        encrypted_token = "encrypted_refresh_token_xyz"

        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = mock_link
            mock_db.commit = MagicMock()
            mock_db.refresh = MagicMock()

            # Act
            result = user_idp_crud.store_user_identity_provider_tokens(
                1, 1, encrypted_token, expires_at, mock_db
            )

        # Assert
        assert result == mock_link
        assert mock_link.idp_refresh_token == encrypted_token
        assert mock_link.idp_access_token_expires_at == expires_at
        assert mock_link.idp_refresh_token_updated_at is not None
        mock_db.commit.assert_called_once()

    def test_store_user_identity_provider_tokens_not_found(self, mock_db):
        """Test storing tokens for non-existent link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when link not found
            - No database operations performed
        """
        # Arrange
        expires_at = datetime.now(timezone.utc)

        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = None

            # Act
            result = user_idp_crud.store_user_identity_provider_tokens(
                1, 1, "token", expires_at, mock_db
            )

        # Assert
        assert result is None
        mock_db.commit.assert_not_called()


class TestClearUserIdentityProviderRefreshToken:
    """Test suite for clear_user_identity_provider_refresh_token_by_user_id_and_idp_id function."""

    def test_clear_user_identity_provider_refresh_token_success(self, mock_db):
        """Test clearing refresh token and metadata.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Token and metadata are cleared
            - Returns True
            - Database commit is called
        """
        # Arrange
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1
        mock_link.idp_refresh_token = "old_token"
        mock_link.idp_access_token_expires_at = datetime.now(timezone.utc)
        mock_link.idp_refresh_token_updated_at = datetime.now(timezone.utc)

        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = mock_link
            mock_db.commit = MagicMock()

            # Act
            result = user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                1, 1, mock_db
            )

        # Assert
        assert result is True
        assert mock_link.idp_refresh_token is None
        assert mock_link.idp_access_token_expires_at is None
        assert mock_link.idp_refresh_token_updated_at is None
        mock_db.commit.assert_called_once()

    def test_clear_user_identity_provider_refresh_token_not_found(self, mock_db):
        """Test clearing token for non-existent link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns False when link not found
            - No database operations performed
        """
        # Arrange
        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = None

            # Act
            result = user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                1, 1, mock_db
            )

        # Assert
        assert result is False
        mock_db.commit.assert_not_called()


class TestDeleteUserIdentityProvider:
    """Test suite for delete_user_identity_provider function."""

    def test_delete_user_identity_provider_success(self, mock_db):
        """Test deleting a user identity provider link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Sensitive data is cleared before deletion
            - Link is deleted from database
            - Returns True
            - Multiple commits are called
        """
        # Arrange
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1
        mock_link.idp_refresh_token = "token"

        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = mock_link
            mock_db.commit = MagicMock()
            mock_db.delete = MagicMock()

            # Act
            result = user_idp_crud.delete_user_identity_provider(1, 1, mock_db)

        # Assert
        assert result is True
        assert mock_link.idp_refresh_token is None
        mock_db.delete.assert_called_once()
        assert mock_db.commit.call_count == 2  # Clear then delete

    def test_delete_user_identity_provider_not_found(self, mock_db):
        """Test deleting non-existent link.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns False when link not found
            - No database operations performed
        """
        # Arrange
        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = None

            # Act
            result = user_idp_crud.delete_user_identity_provider(1, 1, mock_db)

        # Assert
        assert result is False
        mock_db.delete.assert_not_called()

    def test_delete_user_identity_provider_database_error(self, mock_db):
        """Test database error during deletion.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 500 status on database error
            - Rollback is called
        """
        # Arrange
        mock_link = MagicMock(spec=UsersIdentityProvider)
        mock_link.id = 1

        with patch(
            "users.users_identity_providers.crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = mock_link
            mock_db.commit.side_effect = SQLAlchemyError("Database error")
            mock_db.rollback = MagicMock()

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                user_idp_crud.delete_user_identity_provider(1, 1, mock_db)

            assert exc_info.value.status_code == 500
            mock_db.rollback.assert_called_once()
