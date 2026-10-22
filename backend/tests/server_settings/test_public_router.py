"""
Tests for server_settings.public_router module.

This module tests public API endpoints for server settings,
accessible without authentication.
"""

from unittest.mock import patch

import core.exceptions as core_exceptions
import modules.server_settings.schema as server_settings_schema


class TestReadPublicServerSettings:
    """Test suite for read_public_server_settings endpoint."""

    @patch("modules.server_settings.public_router.server_settings_service.get_server_settings_for_public")
    def test_read_public_server_settings_success(self, mock_get_settings, fast_api_client_public, fast_api_app):
        """Test successful retrieval of public server settings."""
        # Arrange
        mock_settings = server_settings_schema.ServerSettingsReadPublic(
            units=server_settings_schema.Units.METRIC,
            public_shareable_links=False,
            public_shareable_links_user_info=False,
            login_photo_set=False,
            currency=server_settings_schema.Currency.EURO,
            num_records_per_page=25,
            signup_enabled=False,
            sso_enabled=False,
            local_login_enabled=True,
            sso_auto_redirect=False,
            tileserver_url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            tileserver_attribution="&copy; OpenStreetMap",
            map_background_color="#dddddd",
            password_type="strict",
            password_length_regular_users=8,
            password_length_admin_users=12,
            allowed_redirect_schemes=["endurain"],
        )

        mock_get_settings.return_value = mock_settings

        # Act
        response = fast_api_client_public.get("/server_settings/public")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["units"] == "metric"
        assert data["public_shareable_links"] is False
        # Ensure sensitive fields are not exposed
        assert "signup_require_admin_approval" not in data
        assert "signup_require_email_verification" not in data
        assert data["allowed_redirect_schemes"] == ["endurain"]

    @patch("modules.server_settings.public_router.server_settings_service.get_server_settings_for_public")
    def test_read_public_server_settings_not_found(
        self, mock_get_settings, fast_api_client_public, fast_api_app_public
    ):
        """Test retrieval when settings not found."""
        # Arrange
        mock_get_settings.side_effect = core_exceptions.NotFoundError("Server settings not found")
        core_exceptions.register_exception_handlers(fast_api_app_public)

        # Act
        response = fast_api_client_public.get("/server_settings/public")

        # Assert
        assert response.status_code == 404


class TestListTileMapsTemplatesPublic:
    """Test suite for list_tile_maps_templates public endpoint."""

    @patch("modules.server_settings.public_router.server_settings_service.get_tile_maps_templates")
    def test_list_tile_maps_templates_public_success(self, mock_get_templates, fast_api_client_public, fast_api_app):
        """Test successful retrieval of tile map templates (public)."""
        # Arrange
        mock_templates = [
            server_settings_schema.TileMapsTemplate(
                template_id="openstreetmap",
                name="OpenStreetMap",
                url_template="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
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
        response = fast_api_client_public.get("/server_settings/public/tile_maps_templates")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["template_id"] == "openstreetmap"
        assert data[1]["template_id"] == "alidade_smooth"

    @patch("modules.server_settings.public_router.server_settings_service.get_tile_maps_templates")
    def test_list_tile_maps_templates_public_empty(self, mock_get_templates, fast_api_client_public, fast_api_app):
        """Test retrieval when no templates available."""
        # Arrange
        mock_get_templates.return_value = []

        # Act
        response = fast_api_client_public.get("/server_settings/public/tile_maps_templates")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
