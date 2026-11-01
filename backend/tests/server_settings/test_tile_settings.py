"""
Tests for server_settings.service reads.

This module tests utility functions for server settings,
including settings retrieval and tile map templates.
"""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.server_settings.models as server_settings_models
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service
import modules.server_settings.tile_service as server_settings_tile_service


class TestGetServerSettings:
    """Test suite for get_server_settings."""

    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_get_server_settings_success(self, mock_crud_get_settings, mock_db):
        """Test successful retrieval of server settings."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.id = 1
        mock_settings.units = 1
        mock_crud_get_settings.return_value = mock_settings

        # Act
        result = server_settings_service.get_server_settings(mock_db)

        # Assert
        assert result == mock_settings
        mock_crud_get_settings.assert_called_once_with(mock_db, for_update=False)

    @patch("modules.server_settings.service.server_settings_crud.get_server_settings")
    def test_get_server_settings_not_found(self, mock_crud_get_settings, mock_db):
        """Test 404 when server settings not found."""
        # Arrange
        mock_crud_get_settings.return_value = None

        # Act & Assert
        with pytest.raises(core_exceptions.ServiceUnavailableError, match="not initialised"):
            server_settings_service.get_server_settings(mock_db)


class TestAllowedTileDomainsForUrl:
    """Test suite for allowed_tile_domains_for_url."""

    def test_a_custom_host_is_added_to_the_builtin_domains(self):
        result = server_settings_tile_service.allowed_tile_domains_for_url("https://tiles.example.com/{z}/{x}/{y}.png")

        assert result[-1] == "https://tiles.example.com"
        assert len(result) == 3

    def test_a_builtin_host_adds_nothing(self):
        result = server_settings_tile_service.allowed_tile_domains_for_url(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        )

        assert len(result) == 2


class TestGetTileMapsTemplates:
    """Test suite for get_tile_maps_templates function."""

    def test_get_tile_maps_templates_returns_list(self):
        """Test that get_tile_maps_templates returns a list."""
        # Act
        result = server_settings_tile_service.get_tile_maps_templates()

        # Assert
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_tile_maps_templates_contains_openstreetmap(self):
        """Test that templates include OpenStreetMap."""
        # Act
        result = server_settings_tile_service.get_tile_maps_templates()

        # Assert
        openstreetmap = next((t for t in result if t.template_id == "openstreetmap"), None)
        assert openstreetmap is not None
        assert openstreetmap.name == "OpenStreetMap"
        assert openstreetmap.url_template == "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        assert openstreetmap.requires_api_key_frontend is False
        assert openstreetmap.requires_api_key_backend is False

    def test_get_tile_maps_templates_contains_alidade_smooth(self):
        """Test that templates include Stadia Maps Alidade Smooth."""
        # Act
        result = server_settings_tile_service.get_tile_maps_templates()

        # Assert
        alidade_smooth = next((t for t in result if t.template_id == "alidade_smooth"), None)
        assert alidade_smooth is not None
        assert alidade_smooth.name == "Stadia Maps Alidade Smooth"
        assert alidade_smooth.requires_api_key_frontend is False
        assert alidade_smooth.requires_api_key_backend is True

    def test_get_tile_maps_templates_contains_alidade_smooth_dark(self):
        """Test that templates include Stadia Maps Alidade Smooth Dark."""
        # Act
        result = server_settings_tile_service.get_tile_maps_templates()

        # Assert
        alidade_dark = next((t for t in result if t.template_id == "alidade_smooth_dark"), None)
        assert alidade_dark is not None
        assert alidade_dark.name == "Stadia Maps Alidade Smooth Dark"
        assert alidade_dark.map_background_color == "#2a2a2a"

    def test_get_tile_maps_templates_contains_alidade_satellite(self):
        """Test that templates include Stadia Maps Alidade Satellite."""
        # Act
        result = server_settings_tile_service.get_tile_maps_templates()

        # Assert
        alidade_satellite = next((t for t in result if t.template_id == "alidade_satellite"), None)
        assert alidade_satellite is not None
        assert alidade_satellite.name == "Stadia Maps Alidade Satellite"
        assert alidade_satellite.requires_api_key_frontend is True
        assert alidade_satellite.requires_api_key_backend is True

    def test_get_tile_maps_templates_contains_stadia_outdoors(self):
        """Test that templates include Stadia Maps Outdoors."""
        # Act
        result = server_settings_tile_service.get_tile_maps_templates()

        # Assert
        stadia_outdoors = next((t for t in result if t.template_id == "stadia_outdoors"), None)
        assert stadia_outdoors is not None
        assert stadia_outdoors.name == "Stadia Maps Outdoors"

    def test_get_tile_maps_templates_all_valid_schemas(self):
        """Test that all templates are valid TileMapsTemplate schemas."""
        # Act
        result = server_settings_tile_service.get_tile_maps_templates()

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
        result = server_settings_tile_service.get_tile_maps_templates()

        # Assert - based on TILE_MAPS_TEMPLATES in utils.py
        assert (
            len(result) == 5
        )  # openstreetmap, alidade_smooth, alidade_smooth_dark, alidade_satellite, stadia_outdoors


class TestExtractDomainFromTileUrl:
    """Test suite for extract_domain_from_tile_url function."""

    def test_extract_domain_with_https(self):
        """Test the tile host itself is the source, not its registrable domain."""
        # Arrange
        url = "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://tiles.stadiamaps.com"

    def test_extract_domain_with_subdomain(self):
        """Test a concrete subdomain is not widened."""
        # Arrange
        url = "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://a.tile.openstreetmap.org"

    def test_extract_domain_without_subdomain(self):
        """Test a single-host URL maps to exactly that host."""
        # Arrange
        url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://tile.openstreetmap.org"

    def test_extract_domain_with_s_placeholder(self):
        """Test {s} widens to the host's own subdomains only."""
        # Arrange
        url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://*.tile.openstreetmap.org"

    def test_extract_domain_localhost_http(self):
        """Test localhost URL returns as-is."""
        # Arrange
        url = "http://localhost:8080/tiles/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "http://localhost:8080"

    def test_extract_domain_localhost_without_port(self):
        """Test localhost without port."""
        # Arrange
        url = "http://localhost/tiles/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "http://localhost"

    def test_extract_domain_ip_address(self):
        """Test IP address returns as-is."""
        # Arrange
        url = "http://127.0.0.1:3000/tiles/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "http://127.0.0.1:3000"

    def test_extract_domain_with_port(self):
        """Test a regular host keeps its port."""
        # Arrange
        url = "https://tiles.example.com:8443/map/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result == "https://tiles.example.com:8443"

    def test_extract_domain_invalid_url_no_scheme(self):
        """Test invalid URL without scheme returns None."""
        # Arrange
        url = "tiles.example.com/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result is None

    def test_extract_domain_empty_string(self):
        """Test empty string returns None."""
        # Arrange
        url = ""

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result is None

    def test_extract_domain_malformed_url(self):
        """Test malformed URL returns None."""
        # Arrange
        url = "not-a-valid-url"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result is None

    @patch("modules.server_settings.tile_service.urlparse")
    def test_extract_domain_exception_handling(self, mock_urlparse):
        """Test that exceptions during parsing are handled gracefully."""
        # Arrange
        mock_urlparse.side_effect = ValueError("Parse error")
        url = "https://tiles.example.com/map/{z}/{x}/{y}.png"

        # Act
        result = server_settings_tile_service.extract_domain_from_tile_url(url)

        # Assert
        assert result is None


class TestExtractDomainDoesNotWidenToAPublicSuffix:
    """The source is never a registrable-domain wildcard."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://tiles.example.co.uk/{z}/{x}/{y}.png", "https://tiles.example.co.uk"),
            ("https://{s}.tiles.example.co.uk/{z}/{x}/{y}.png", "https://*.tiles.example.co.uk"),
            ("http://10.0.0.5:8080/{z}/{x}/{y}.png", "http://10.0.0.5:8080"),
            ("http://[::1]:8080/{z}/{x}/{y}.png", "http://[::1]:8080"),
        ],
    )
    def test_source_is_the_host(self, url, expected):
        assert server_settings_tile_service.extract_domain_from_tile_url(url) == expected


class TestGetAllowedTileDomains:
    """Test suite for get_allowed_tile_domains function."""

    @patch("modules.server_settings.service.get_server_settings")
    def test_get_allowed_tile_domains_with_custom_domain(self, mock_get_settings, mock_db):
        """Test that custom tile domain is added to allowed list."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = "https://custom.tiles.com/map/{z}/{x}/{y}.png"
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_service.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert "https://custom.tiles.com" in result
        assert len(result) == 3

    @patch("modules.server_settings.service.get_server_settings")
    def test_get_allowed_tile_domains_with_builtin_domain(self, mock_get_settings, mock_db):
        """Test that builtin domains are not duplicated."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}.png"
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_service.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        # Should not duplicate stadiamaps.com
        assert result.count("https://*.stadiamaps.com") == 1
        assert len(result) == 2

    @patch("modules.server_settings.service.get_server_settings")
    def test_get_allowed_tile_domains_with_localhost(self, mock_get_settings, mock_db):
        """Test that localhost URLs are added correctly."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = "http://localhost:8080/tiles/{z}/{x}/{y}.png"
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_service.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert "http://localhost:8080" in result
        assert len(result) == 3

    @patch("modules.server_settings.service.get_server_settings")
    def test_get_allowed_tile_domains_invalid_url(self, mock_get_settings, mock_db):
        """Test that invalid custom URLs are ignored."""
        # Arrange
        mock_settings = MagicMock(spec=server_settings_models.ServerSettings)
        mock_settings.tileserver_url = "not-a-valid-url"
        mock_get_settings.return_value = mock_settings

        # Act
        result = server_settings_service.get_allowed_tile_domains(mock_db)

        # Assert
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert len(result) == 2

    @patch("modules.server_settings.service.get_server_settings")
    def test_get_allowed_tile_domains_db_error(self, mock_get_settings, mock_db):
        """Test a missing settings row falls back to the built-in domains."""
        # Arrange
        mock_get_settings.side_effect = core_exceptions.ServiceUnavailableError("Server settings are not initialised.")

        # Act
        result = server_settings_service.get_allowed_tile_domains(mock_db)

        # Assert - should return builtins as fallback
        assert "https://*.openstreetmap.org" in result
        assert "https://*.stadiamaps.com" in result
        assert len(result) == 2
