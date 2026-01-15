"""
Tests for server_settings.public_router module.

This module tests public API endpoints for server settings,
accessible without authentication.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status

import server_settings.schema as server_settings_schema
import server_settings.models as server_settings_models


class TestReadPublicServerSettings:
    """Test suite for read_public_server_settings endpoint."""

    @patch(
        "server_settings.public_router.server_settings_utils.get_server_settings_or_404"
    )
    def test_read_public_server_settings_success(
        self, mock_get_settings, fast_api_client_public, fast_api_app
    ):
        """Test successful retrieval of public server settings."""
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

        mock_get_settings.return_value = mock_settings

        # Act
        response = fast_api_client_public.get("/server_settings/public")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["units"] == 1
        assert data["public_shareable_links"] is False
        # Ensure sensitive fields are not exposed
        assert "signup_require_admin_approval" not in data
        assert "signup_require_email_verification" not in data

    @patch(
        "server_settings.public_router.server_settings_utils.get_server_settings_or_404"
    )
    def test_read_public_server_settings_not_found(
        self, mock_get_settings, fast_api_client_public, fast_api_app
    ):
        """Test retrieval when settings not found."""
        # Arrange
        mock_get_settings.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server settings not found",
        )

        # Act
        response = fast_api_client_public.get("/server_settings/public")

        # Assert
        assert response.status_code == 404


class TestListTileMapsTemplatesPublic:
    """Test suite for list_tile_maps_templates public endpoint."""

    @patch(
        "server_settings.public_router.server_settings_utils.get_tile_maps_templates"
    )
    def test_list_tile_maps_templates_public_success(
        self, mock_get_templates, fast_api_client_public, fast_api_app
    ):
        """Test successful retrieval of tile map templates (public)."""
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
        response = fast_api_client_public.get(
            "/server_settings/public/tile_maps_templates"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["template_id"] == "openstreetmap"
        assert data[1]["template_id"] == "alidade_smooth"

    @patch(
        "server_settings.public_router.server_settings_utils.get_tile_maps_templates"
    )
    def test_list_tile_maps_templates_public_empty(
        self, mock_get_templates, fast_api_client_public, fast_api_app
    ):
        """Test retrieval when no templates available."""
        # Arrange
        mock_get_templates.return_value = []

        # Act
        response = fast_api_client_public.get(
            "/server_settings/public/tile_maps_templates"
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
