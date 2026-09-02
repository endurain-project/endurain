"""
Tests for server_settings.router module.

This module tests API endpoints for server settings management,
including read, update, and file upload operations.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException, status

import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema


class TestReadServerSettings:
    """Test suite for read_server_settings endpoint."""

    @patch("modules.server_settings.router.server_settings_utils.get_server_settings_for_admin")
    def test_read_server_settings_success(self, mock_get_settings, fast_api_client, fast_api_app):
        """Test successful retrieval of server settings."""
        # Arrange
        mock_settings = server_settings_schema.ServerSettingsRead(
            id=1,
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            signup_require_admin_approval=True,
            signup_require_email_verification=True,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="&copy; OpenStreetMap",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
            tileserver_api_key=None,
        )

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
        assert data["units"] == "metric"
        assert data["public_shareable_links"] is False

    @patch("modules.server_settings.router.server_settings_utils.get_server_settings_or_404")
    def test_read_server_settings_not_found(self, mock_get_settings, fast_api_client, fast_api_app):
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

    @patch("modules.server_settings.router.server_settings_utils.get_tile_maps_templates")
    def test_list_tile_maps_templates_success(self, mock_get_templates, fast_api_client, fast_api_app):
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

    @patch("modules.server_settings.router.server_settings_service.edit_server_settings")
    def test_edit_server_settings_success(self, mock_edit_settings, fast_api_client, fast_api_app):
        """Test successful update of server settings."""
        # Arrange
        mock_updated_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_updated_settings.id = 1
        mock_updated_settings.units = "imperial"
        mock_updated_settings.public_shareable_links = True
        mock_updated_settings.public_shareable_links_user_info = True
        mock_updated_settings.login_photo_set = False
        mock_updated_settings.currency = "dollar"
        mock_updated_settings.num_records_per_page = 50
        mock_updated_settings.signup_enabled = True
        mock_updated_settings.signup_require_admin_approval = False
        mock_updated_settings.signup_require_email_verification = True
        mock_updated_settings.sso_enabled = False
        mock_updated_settings.local_login_enabled = True
        mock_updated_settings.sso_auto_redirect = False
        mock_updated_settings.tileserver_url = "https://tiles.example.com/{z}/{x}/{y}.png"
        mock_updated_settings.tileserver_attribution = "&copy; Example"
        mock_updated_settings.map_background_color = "#000000"
        mock_updated_settings.password_type = "length_only"
        mock_updated_settings.password_length_regular_users = 10
        mock_updated_settings.password_length_admin_users = 15
        mock_updated_settings.tileserver_api_key = None
        mock_updated_settings.tileserver_regenerate_thumbnails_on_change = False

        mock_edit_settings.return_value = mock_updated_settings

        # Act
        response = fast_api_client.put(
            "/server_settings",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "id": 1,
                "units": "imperial",
                "public_shareable_links": True,
                "public_shareable_links_user_info": True,
                "login_photo_set": False,
                "currency": "dollar",
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
        assert response.status_code == 200
        data = response.json()
        assert data["units"] == "imperial"
        assert data["num_records_per_page"] == 50

    @patch("modules.server_settings.router.server_settings_service.edit_server_settings")
    def test_edit_server_settings_not_found(self, mock_edit_settings, fast_api_client, fast_api_app):
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
                "units": "imperial",
                "public_shareable_links": True,
                "public_shareable_links_user_info": True,
                "login_photo_set": False,
                "currency": "dollar",
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


class TestDeleteLoginPhoto:
    """Test suite for delete_login_photo endpoint."""

    @patch(
        "modules.server_settings.router.core_file_uploads.delete_files_by_pattern",
        new_callable=AsyncMock,
    )
    def test_delete_login_photo_success(self, mock_delete, fast_api_client, fast_api_app):
        """Test successful deletion of login photo."""
        # Act
        response = fast_api_client.delete(
            "/server_settings/upload/login",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204

    @patch(
        "modules.server_settings.router.core_file_uploads.delete_files_by_pattern",
        new_callable=AsyncMock,
    )
    def test_delete_login_photo_not_exists(self, mock_delete, fast_api_client, fast_api_app):
        """Test deletion when photo doesn't exist."""
        # Act
        response = fast_api_client.delete(
            "/server_settings/upload/login",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
