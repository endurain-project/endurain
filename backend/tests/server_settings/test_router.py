"""
Tests for server_settings.router module.

This module tests API endpoints for server settings management,
including read, update, and file upload operations.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException, status, UploadFile
from io import BytesIO

import server_settings.schema as server_settings_schema
import server_settings.models as server_settings_models


class TestReadServerSettings:
    """Test suite for read_server_settings endpoint."""

    @patch("server_settings.router.server_settings_utils.get_server_settings")
    def test_read_server_settings_success(
        self, mock_get_settings, fast_api_client, fast_api_app
    ):
        """Test successful retrieval of server settings."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.id = 1
        mock_settings.units = 1
        mock_settings.public_shareable_links = False
        mock_settings.public_shareable_links_user_info = False
        mock_settings.login_photo_set = False
        mock_settings.currency = 1
        mock_settings.num_records_per_page = 25
        mock_settings.signup_enabled = False
        mock_settings.signup_require_admin_approval = True
        mock_settings.signup_require_email_verification = True
        mock_settings.sso_enabled = False
        mock_settings.local_login_enabled = True
        mock_settings.sso_auto_redirect = False
        mock_settings.tileserver_url = (
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        )
        mock_settings.tileserver_attribution = "&copy; OpenStreetMap"
        mock_settings.map_background_color = "#dddddd"
        mock_settings.password_type = "strict"
        mock_settings.password_length_regular_users = 8
        mock_settings.password_length_admin_users = 12
        mock_settings.tileserver_api_key = None

        mock_get_settings.return_value = mock_settings

        # Act
        response = fast_api_client.get(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["units"] == 1
        assert data["public_shareable_links"] is False

    @patch("server_settings.router.server_settings_utils.get_server_settings")
    def test_read_server_settings_not_found(
        self, mock_get_settings, fast_api_client, fast_api_app
    ):
        """Test retrieval when settings not found."""
        # Arrange
        mock_get_settings.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server settings not found",
        )

        # Act
        response = fast_api_client.get(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestListTileMapsTemplates:
    """Test suite for list_tile_maps_templates endpoint."""

    @patch("server_settings.router.server_settings_utils.get_tile_maps_templates")
    def test_list_tile_maps_templates_success(
        self, mock_get_templates, fast_api_client, fast_api_app
    ):
        """Test successful retrieval of tile map templates."""
        # Arrange
        mock_templates = [
            server_settings_schema.TileMapsTemplate(
                template_id="openstreetmap",
                name="OpenStreetMap",
                url_template="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                attribution="&copy; OpenStreetMap",
                map_background_color="#e8e8e8",
                requires_api_key_frontend=False,
                requires_api_key_backend=False,
            ),
            server_settings_schema.TileMapsTemplate(
                template_id="alidade_smooth",
                name="Stadia Maps Alidade Smooth",
                url_template="https://tiles.stadiamaps.com/{z}/{x}/{y}.png",
                attribution="&copy; Stadia Maps",
                map_background_color="#f5f5f5",
                requires_api_key_frontend=False,
                requires_api_key_backend=True,
            ),
        ]
        mock_get_templates.return_value = mock_templates

        # Act
        response = fast_api_client.get(
            "/server_settings/tile_maps_templates",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["template_id"] == "openstreetmap"
        assert data[1]["template_id"] == "alidade_smooth"


class TestEditServerSettings:
    """Test suite for edit_server_settings endpoint."""

    @patch("server_settings.router.server_settings_crud.edit_server_settings")
    def test_edit_server_settings_success(
        self, mock_edit_settings, fast_api_client, fast_api_app
    ):
        """Test successful update of server settings."""
        # Arrange
        mock_updated_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_updated_settings.id = 1
        mock_updated_settings.units = 2
        mock_updated_settings.public_shareable_links = True
        mock_updated_settings.public_shareable_links_user_info = True
        mock_updated_settings.login_photo_set = False
        mock_updated_settings.currency = 2
        mock_updated_settings.num_records_per_page = 50
        mock_updated_settings.signup_enabled = True
        mock_updated_settings.signup_require_admin_approval = False
        mock_updated_settings.signup_require_email_verification = True
        mock_updated_settings.sso_enabled = False
        mock_updated_settings.local_login_enabled = True
        mock_updated_settings.sso_auto_redirect = False
        mock_updated_settings.tileserver_url = (
            "https://tiles.example.com/{z}/{x}/{y}.png"
        )
        mock_updated_settings.tileserver_attribution = "&copy; Example"
        mock_updated_settings.map_background_color = "#000000"
        mock_updated_settings.password_type = "length_only"
        mock_updated_settings.password_length_regular_users = 10
        mock_updated_settings.password_length_admin_users = 15
        mock_updated_settings.tileserver_api_key = None

        mock_edit_settings.return_value = mock_updated_settings

        # Act
        response = fast_api_client.put(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "id": 1,
                "units": 2,
                "public_shareable_links": True,
                "public_shareable_links_user_info": True,
                "login_photo_set": False,
                "currency": 2,
                "num_records_per_page": 50,
                "signup_enabled": True,
                "signup_require_admin_approval": False,
                "signup_require_email_verification": True,
                "sso_enabled": False,
                "local_login_enabled": True,
                "sso_auto_redirect": False,
                "tileserver_url": "https://tiles.example.com/{z}/{x}/{y}.png",
                "tileserver_attribution": "&copy; Example",
                "map_background_color": "#000000",
                "password_type": "length_only",
                "password_length_regular_users": 10,
                "password_length_admin_users": 15,
            },
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["units"] == 2
        assert data["num_records_per_page"] == 50

    @patch("server_settings.router.server_settings_crud.edit_server_settings")
    def test_edit_server_settings_not_found(
        self, mock_edit_settings, fast_api_client, fast_api_app
    ):
        """Test update when settings not found."""
        # Arrange
        mock_edit_settings.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server settings not found",
        )

        # Act
        response = fast_api_client.put(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "id": 1,
                "units": 2,
                "public_shareable_links": True,
                "public_shareable_links_user_info": True,
                "login_photo_set": False,
                "currency": 2,
                "num_records_per_page": 50,
                "signup_enabled": True,
                "signup_require_admin_approval": False,
                "signup_require_email_verification": True,
                "sso_enabled": False,
                "local_login_enabled": True,
                "sso_auto_redirect": False,
                "tileserver_url": "https://tiles.example.com/{z}/{x}/{y}.png",
                "tileserver_attribution": "&copy; Example",
                "map_background_color": "#000000",
                "password_type": "length_only",
                "password_length_regular_users": 10,
                "password_length_admin_users": 15,
            },
        )

        # Assert
        assert response.status_code == 404


class TestUploadLoginPhoto:
    """Test suite for upload_login_photo endpoint."""

    @pytest.mark.skip(
        reason="Complex async file upload mocking - tested via integration tests"
    )
    def test_upload_login_photo_success(
        self,
        fast_api_client,
        fast_api_app,
    ):
        """Test successful upload of login photo."""
        # This endpoint requires complex async file I/O mocking
        # File upload functionality is better tested via integration tests
        pass


class TestDeleteLoginPhoto:
    """Test suite for delete_login_photo endpoint."""

    @patch("server_settings.router.aiofiles.os.remove", new_callable=AsyncMock)
    @patch("server_settings.router.os.path.exists")
    def test_delete_login_photo_success(
        self, mock_exists, mock_remove, fast_api_client, fast_api_app
    ):
        """Test successful deletion of login photo."""
        # Arrange
        mock_exists.return_value = True

        # Act
        response = fast_api_client.delete(
            "/server_settings/upload/login",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch("server_settings.router.os.path.exists")
    def test_delete_login_photo_not_exists(
        self, mock_exists, fast_api_client, fast_api_app
    ):
        """Test deletion when photo doesn't exist."""
        # Arrange
        mock_exists.return_value = False

        # Act
        response = fast_api_client.delete(
            "/server_settings/upload/login",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
