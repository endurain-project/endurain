"""
Tests for server_settings.utils module.

This module tests utility functions for server settings,
including settings retrieval and tile map templates.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status

import server_settings.utils as server_settings_utils
import server_settings.schema as server_settings_schema
import server_settings.models as server_settings_models


class TestGetServerSettings:
    """Test suite for get_server_settings utility function."""

    @patch("server_settings.utils.server_settings_crud.get_server_settings")
    def test_get_server_settings_success(self, mock_crud_get_settings, mock_db):
        """Test successful retrieval of server settings."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.id = 1
        mock_settings.units = 1
        mock_crud_get_settings.return_value = mock_settings

        # Act
        result = server_settings_utils.get_server_settings(mock_db)

        # Assert
        assert result == mock_settings
        mock_crud_get_settings.assert_called_once_with(mock_db)

    @patch("server_settings.utils.server_settings_crud.get_server_settings")
    def test_get_server_settings_not_found(self, mock_crud_get_settings, mock_db):
        """Test 404 when server settings not found."""
        # Arrange
        mock_crud_get_settings.return_value = None

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            server_settings_utils.get_server_settings(mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "Server settings not found"


class TestGetTileMapsTemplates:
    """Test suite for get_tile_maps_templates function."""

    def test_get_tile_maps_templates_returns_list(self):
        """Test that get_tile_maps_templates returns a list."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_tile_maps_templates_contains_openstreetmap(self):
        """Test that templates include OpenStreetMap."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert
        openstreetmap = next(
            (t for t in result if t.template_id == "openstreetmap"), None
        )
        assert openstreetmap is not None
        assert openstreetmap.name == "OpenStreetMap"
        assert (
            openstreetmap.url_template
            == "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        )
        assert openstreetmap.requires_api_key_frontend is False
        assert openstreetmap.requires_api_key_backend is False

    def test_get_tile_maps_templates_contains_alidade_smooth(self):
        """Test that templates include Stadia Maps Alidade Smooth."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert
        alidade_smooth = next(
            (t for t in result if t.template_id == "alidade_smooth"), None
        )
        assert alidade_smooth is not None
        assert alidade_smooth.name == "Stadia Maps Alidade Smooth"
        assert alidade_smooth.requires_api_key_frontend is False
        assert alidade_smooth.requires_api_key_backend is True

    def test_get_tile_maps_templates_contains_alidade_smooth_dark(self):
        """Test that templates include Stadia Maps Alidade Smooth Dark."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert
        alidade_dark = next(
            (t for t in result if t.template_id == "alidade_smooth_dark"), None
        )
        assert alidade_dark is not None
        assert alidade_dark.name == "Stadia Maps Alidade Smooth Dark"
        assert alidade_dark.map_background_color == "#2a2a2a"

    def test_get_tile_maps_templates_contains_alidade_satellite(self):
        """Test that templates include Stadia Maps Alidade Satellite."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert
        alidade_satellite = next(
            (t for t in result if t.template_id == "alidade_satellite"), None
        )
        assert alidade_satellite is not None
        assert alidade_satellite.name == "Stadia Maps Alidade Satellite"
        assert alidade_satellite.requires_api_key_frontend is True
        assert alidade_satellite.requires_api_key_backend is True

    def test_get_tile_maps_templates_contains_stadia_outdoors(self):
        """Test that templates include Stadia Maps Outdoors."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert
        stadia_outdoors = next(
            (t for t in result if t.template_id == "stadia_outdoors"), None
        )
        assert stadia_outdoors is not None
        assert stadia_outdoors.name == "Stadia Maps Outdoors"

    def test_get_tile_maps_templates_all_valid_schemas(self):
        """Test that all templates are valid TileMapsTemplate schemas."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert
        for template in result:
            assert isinstance(template, server_settings_schema.TileMapsTemplate)
            assert hasattr(template, "template_id")
            assert hasattr(template, "name")
            assert hasattr(template, "url_template")
            assert hasattr(template, "attribution")
            assert hasattr(template, "map_background_color")
            assert hasattr(template, "requires_api_key_frontend")
            assert hasattr(template, "requires_api_key_backend")

    def test_get_tile_maps_templates_expected_count(self):
        """Test that we get the expected number of templates."""
        # Act
        result = server_settings_utils.get_tile_maps_templates()

        # Assert - based on TILE_MAPS_TEMPLATES in utils.py
        assert (
            len(result) == 5
        )  # openstreetmap, alidade_smooth, alidade_smooth_dark, alidade_satellite, stadia_outdoors
