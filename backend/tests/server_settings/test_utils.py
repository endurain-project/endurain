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


class TestExtractDomainFromTileUrl:
    """Test suite for extract_domain_from_tile_url function."""

    def test_extract_domain_with_https(self):
        """Test domain extraction from HTTPS URL extracts base domain."""
        # Arrange
        url = "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://*.stadiamaps.com"

    def test_extract_domain_with_subdomain(self):
        """Test domain extraction uses base domain for wildcard."""
        # Arrange
        url = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://*.openstreetmap.org"

    def test_extract_domain_with_s_placeholder(self):
        """Test domain extraction handles {s} placeholder."""
        # Arrange
        url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://*.openstreetmap.org"

    def test_extract_domain_localhost_http(self):
        """Test localhost URL returns as-is."""
        # Arrange
        url = "http://localhost:8080/tiles/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result == "http://localhost:8080"

    def test_extract_domain_localhost_without_port(self):
        """Test localhost without port."""
        # Arrange
        url = "http://localhost/tiles/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result == "http://localhost"

    def test_extract_domain_ip_address(self):
        """Test IP address returns as-is."""
        # Arrange
        url = "http://127.0.0.1:3000/tiles/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result == "http://127.0.0.1:3000"

    def test_extract_domain_with_port(self):
        """Test regular domain with port uses base domain."""
        # Arrange
        url = "https://tiles.example.com:8443/map/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://*.example.com"

    def test_extract_domain_invalid_url_no_scheme(self):
        """Test invalid URL without scheme returns None."""
        # Arrange
        url = "tiles.example.com/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result is None

    def test_extract_domain_empty_string(self):
        """Test empty string returns None."""
        # Arrange
        url = ""

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result is None

    def test_extract_domain_malformed_url(self):
        """Test malformed URL returns None."""
        # Arrange
        url = "not-a-valid-url"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result is None

    @patch("server_settings.utils.urlparse")
    def test_extract_domain_exception_handling(self, mock_urlparse):
        """Test that exceptions during parsing are handled gracefully."""
        # Arrange
        mock_urlparse.side_effect = Exception("Parse error")
        url = "https://tiles.example.com/map/{z}/{x}/{y}.png"

        # Act
        result = server_settings_utils.extract_domain_from_tile_url(url)

        # Assert
        assert result is None


class TestGetAllowedTileDomains:
    """Test suite for get_allowed_tile_domains function."""

    @patch("server_settings.utils.get_server_settings")
    def test_get_allowed_tile_domains_with_custom_domain(
        self, mock_get_settings, mock_db
    ):
        """Test that custom tile domain is added to allowed list."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = "https://custom.tiles.com/map/{z}/{x}/{y}.png"
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_utils.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert "https://*.tiles.com" in result
        assert len(result) == 3

    @patch("server_settings.utils.get_server_settings")
    def test_get_allowed_tile_domains_with_builtin_domain(
        self, mock_get_settings, mock_db
    ):
        """Test that builtin domains are not duplicated."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = (
            "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}.png"
        )
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_utils.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        # Should not duplicate stadiamaps.com
        assert result.count("https://*.stadiamaps.com") == 1
        assert len(result) == 2

    @patch("server_settings.utils.get_server_settings")
    def test_get_allowed_tile_domains_with_localhost(self, mock_get_settings, mock_db):
        """Test that localhost URLs are added correctly."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = "http://localhost:8080/tiles/{z}/{x}/{y}.png"
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_utils.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert "http://localhost:8080" in result
        assert len(result) == 3

    @patch("server_settings.utils.get_server_settings")
    def test_get_allowed_tile_domains_no_custom_domain(
        self, mock_get_settings, mock_db
    ):
        """Test that only builtins are returned when no custom domain."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = None
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_utils.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert len(result) == 2

    @patch("server_settings.utils.get_server_settings")
    def test_get_allowed_tile_domains_invalid_url(self, mock_get_settings, mock_db):
        """Test that invalid custom URLs are ignored."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = "not-a-valid-url"
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_utils.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert len(result) == 2

    @patch("server_settings.utils.get_server_settings")
    def test_get_allowed_tile_domains_db_error(self, mock_get_settings, mock_db):
        """Test that DB errors are handled gracefully."""
        # Arrange
        mock_get_settings.side_effect = Exception("Database error")

        # Act
        result = server_settings_utils.get_allowed_tile_domains(mock_db)

        # Assert - should return builtins as fallback
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert len(result) == 2
