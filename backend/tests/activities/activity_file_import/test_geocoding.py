"""Tests for reverse-geocoding in activity_file_import.utils.

Relocated from ``tests/activities/activity/test_utils*`` when
``location_based_on_coordinates`` moved out of the activities core into the
parsing layer (co-located with its only caller ``resolve_location``).
"""

from unittest.mock import MagicMock, patch


class TestLocationBasedOnCoordinates:
    """All providers, rate limiting, and error handling."""

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch("modules.activities.activity_file_import.utils.core_config")
    def test_location_missing_coords(self, mock_config):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        result = location_based_on_coordinates(None, None)

        assert result is None

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.GEOCODES_MAPS_API", "changeme")
    @patch("modules.activities.activity_file_import.utils.core_config")
    def test_location_geocode_api_key_changeme(self, mock_config):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "unsupported")
    @patch("modules.activities.activity_file_import.utils.core_config")
    def test_location_unsupported_provider(self, mock_config):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(
        "modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_HOST",
        "nominatim.openstreetmap.org",
    )
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_nominatim_success(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {"city": "Lisbon", "town": "Belem", "country": "Portugal"}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": "Belem", "country": "Portugal"}

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(
        "modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_HOST",
        "nominatim.openstreetmap.org",
    )
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_nominatim_empty_address_returns_none(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", False)
    @patch("modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_HOST", "localhost")
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_nominatim_http_protocol(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {"city": "Lisbon", "country": "Portugal"}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": None, "country": "Portugal"}

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.PHOTON_API_USE_HTTPS", True)
    @patch("modules.activities.activity_file_import.utils.core_config.settings.PHOTON_API_HOST", "photon.komoot.io")
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_photon_success(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "features": [{"properties": {"district": "Lisbon", "city": "Belem", "country": "Portugal"}}]
        }
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": "Belem", "country": "Portugal"}

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.PHOTON_API_USE_HTTPS", False)
    @patch("modules.activities.activity_file_import.utils.core_config.settings.PHOTON_API_HOST", "localhost")
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_photon_http_protocol(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"features": [{"properties": {"country": "Test"}}]}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(0.0, 0.0)

        assert result == {"city": None, "town": None, "country": "Test"}

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.PHOTON_API_USE_HTTPS", True)
    @patch("modules.activities.activity_file_import.utils.core_config.settings.PHOTON_API_HOST", "photon.komoot.io")
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_photon_no_features_returns_none(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"features": []}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.GEOCODES_MAPS_API", "valid_key")
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_geocode_success(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_response = MagicMock()
        mock_response.json.return_value = {"address": {"city": "Lisbon", "country": "Portugal"}}
        mock_get.return_value = mock_response

        result = location_based_on_coordinates(38.0, -9.0)

        assert result == {"city": "Lisbon", "town": None, "country": "Portugal"}

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(
        "modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_HOST",
        "nominatim.openstreetmap.org",
    )
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    def test_nominatim_http_error_returns_none(self, mock_get):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        mock_get.side_effect = Exception("Connection error")

        result = location_based_on_coordinates(38.0, -9.0)

        assert result is None

    @patch("modules.activities.activity_file_import.utils.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch("modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(
        "modules.activities.activity_file_import.utils.core_config.settings.NOMINATIM_API_HOST",
        "nominatim.openstreetmap.org",
    )
    @patch("modules.activities.activity_file_import.utils.core_config.API_VERSION", "1.0")
    @patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_LOCK")
    @patch("modules.activities.activity_file_import.utils.requests.get")
    @patch("modules.activities.activity_file_import.utils.time.sleep")
    @patch("modules.activities.activity_file_import.utils.time.monotonic")
    def test_rate_limiting_applied(self, mock_monotonic, mock_sleep, mock_get, mock_lock):
        from modules.activities.activity_file_import.utils import location_based_on_coordinates

        with (
            patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_MIN_INTERVAL", 1),
            patch("modules.activities.activity_file_import.utils.core_config.REVERSE_GEO_LAST_CALL", 0),
        ):
            mock_lock.__enter__.return_value = None
            mock_lock.__exit__.return_value = None
            mock_monotonic.side_effect = [0.5, 0.5]

            mock_response = MagicMock()
            mock_response.json.return_value = {"address": {"country": "Test"}}
            mock_get.return_value = mock_response

            result = location_based_on_coordinates(0.0, 0.0)

            assert result is not None
            mock_sleep.assert_called_once()
