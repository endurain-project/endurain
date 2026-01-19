"""
Tests for server_settings.crud module.

This module tests CRUD operations for server settings,
including retrieval and update operations.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

import server_settings.crud as server_settings_crud
import server_settings.schema as server_settings_schema
import server_settings.models as server_settings_models


class TestGetServerSettings:
    """Test suite for get_server_settings function."""

    def test_get_server_settings_success(self, mock_db):
        """Test successful retrieval of server settings."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.id = 1
        mock_settings.units = 1
        mock_settings.public_shareable_links = False

        mock_execute = MagicMock()
        mock_execute.scalar_one_or_none.return_value = mock_settings
        mock_db.execute.return_value = mock_execute

        # Act
        result = server_settings_crud.get_server_settings(mock_db)

        # Assert
        assert result == mock_settings
        mock_db.execute.assert_called_once()

    def test_get_server_settings_not_found(self, mock_db):
        """Test retrieval when settings don't exist."""
        # Arrange
        mock_execute = MagicMock()
        mock_execute.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_execute

        # Act
        result = server_settings_crud.get_server_settings(mock_db)

        # Assert
        assert result is None

    def test_get_server_settings_exception(self, mock_db):
        """Test exception handling in get_server_settings."""
        # Arrange
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            server_settings_crud.get_server_settings(mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestEditServerSettings:
    """Test suite for edit_server_settings function."""

    @patch("server_settings.crud.get_server_settings")
    def test_edit_server_settings_success(self, mock_get_settings, mock_db):
        """Test successful update of server settings."""
        # Arrange
        mock_existing_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_existing_settings.id = 1
        mock_existing_settings.units = 1
        mock_existing_settings.public_shareable_links = False
        mock_existing_settings.num_records_per_page = 25
        mock_existing_settings.signup_enabled = False

        mock_get_settings.return_value = mock_existing_settings

        update_data = server_settings_schema.ServerSettingsEdit(
            id=1,
            units=server_settings_schema.Units.IMPERIAL,
            public_shareable_links=True,
            public_shareable_links_user_info=True,
            login_photo_set=False,
            currency=server_settings_schema.Currency.DOLLAR,
            num_records_per_page=50,
            signup_enabled=True,
            signup_require_admin_approval=False,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )

        # Act
        result = server_settings_crud.edit_server_settings(update_data, mock_db)

        # Assert
        assert result == mock_existing_settings
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_existing_settings)

    @patch("server_settings.crud.get_server_settings")
    def test_edit_server_settings_not_found(self, mock_get_settings, mock_db):
        """Test update when settings don't exist."""
        # Arrange
        mock_get_settings.return_value = None

        update_data = server_settings_schema.ServerSettingsEdit(
            id=1,
            units=server_settings_schema.Units.IMPERIAL,
            public_shareable_links=True,
            public_shareable_links_user_info=True,
            login_photo_set=False,
            currency=server_settings_schema.Currency.DOLLAR,
            num_records_per_page=50,
            signup_enabled=True,
            signup_require_admin_approval=False,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            server_settings_crud.edit_server_settings(update_data, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Server settings not found"

    @patch("server_settings.crud.get_server_settings")
    def test_edit_server_settings_partial_update(self, mock_get_settings, mock_db):
        """Test partial update of server settings."""
        # Arrange
        mock_existing_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_existing_settings.id = 1
        mock_existing_settings.units = 1
        mock_existing_settings.num_records_per_page = 25

        mock_get_settings.return_value = mock_existing_settings

        # Create update with only some fields
        update_data = server_settings_schema.ServerSettingsEdit(
            id=1,
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=50,  # Only this changes
            signup_enabled=False,
            signup_require_admin_approval=True,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )

        # Act
        result = server_settings_crud.edit_server_settings(update_data, mock_db)

        # Assert
        assert result == mock_existing_settings
        mock_db.commit.assert_called_once()

    @patch("server_settings.crud.get_server_settings")
    def test_edit_server_settings_database_error(self, mock_get_settings, mock_db):
        """Test database error during update."""
        # Arrange
        mock_existing_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_get_settings.return_value = mock_existing_settings
        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        update_data = server_settings_schema.ServerSettingsEdit(
            id=1,
            units=server_settings_schema.Units.IMPERIAL,
            public_shareable_links=True,
            public_shareable_links_user_info=True,
            login_photo_set=False,
            currency=server_settings_schema.Currency.DOLLAR,
            num_records_per_page=50,
            signup_enabled=True,
            signup_require_admin_approval=False,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="Test",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            server_settings_crud.edit_server_settings(update_data, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()
