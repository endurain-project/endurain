"""Tests for the activity reverse-geocoding service.

Covers the provider request building (incl. the SSRF host allow-list and
redirect hardening), response parsing, throttling, and the create-path /
backfill store paths. Relocated from
``tests/activities/activity_file_import/test_geocoding.py`` when reverse-geocoding
moved off the parse path into the ``activity_geocoding`` subscriber (module rework
plan A4d).
"""

from unittest.mock import MagicMock, patch

from modules.activities.activity_geocoding.service import (
    LocationResult,
    _is_valid_host,
    _resolves_to_blocked_ip,
    backfill_missing_activity_locations,
    geocode_and_store_activity_location,
    reverse_geocode,
)

_SVC = "modules.activities.activity_geocoding.service"


class TestReverseGeocode:
    """All providers, host validation, rate limiting, and error handling."""

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    def test_missing_coords_returns_none(self):
        assert reverse_geocode(None, None) is None

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch(f"{_SVC}.core_config.settings.GEOCODES_MAPS_API", "changeme")
    def test_geocode_api_key_changeme_returns_none(self):
        assert reverse_geocode(38.0, -9.0) is None

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "unsupported")
    def test_unsupported_provider_returns_none(self):
        assert reverse_geocode(38.0, -9.0) is None

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: False)
    @patch(f"{_SVC}.requests.get")
    def test_nominatim_success(self, mock_get):
        mock_get.return_value.json.return_value = {
            "address": {"city": "Lisbon", "town": "Belem", "country": "Portugal"}
        }
        result = reverse_geocode(38.0, -9.0)
        assert result == LocationResult(city="Lisbon", town="Belem", country="Portugal")

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_USE_HTTPS", False)
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "nominatim.local")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: False)
    @patch(f"{_SVC}.requests.get")
    def test_nominatim_http_protocol(self, mock_get):
        mock_get.return_value.json.return_value = {"address": {"city": "Lisbon", "country": "Portugal"}}
        result = reverse_geocode(38.0, -9.0)
        assert result == LocationResult(city="Lisbon", town=None, country="Portugal")
        # http (not https) when NOMINATIM_API_USE_HTTPS is False.
        assert mock_get.call_args.args[0].startswith("http://nominatim.local/reverse?")

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: False)
    @patch(f"{_SVC}.requests.get")
    def test_nominatim_empty_address_returns_none(self, mock_get):
        mock_get.return_value.json.return_value = {"address": {}}
        assert reverse_geocode(38.0, -9.0) is None

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch(f"{_SVC}.core_config.settings.PHOTON_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.PHOTON_API_HOST", "photon.komoot.io")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: False)
    @patch(f"{_SVC}.requests.get")
    def test_photon_success(self, mock_get):
        mock_get.return_value.json.return_value = {
            "features": [{"properties": {"district": "Lisbon", "city": "Belem", "country": "Portugal"}}]
        }
        result = reverse_geocode(38.0, -9.0)
        assert result == LocationResult(city="Lisbon", town="Belem", country="Portugal")

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "photon")
    @patch(f"{_SVC}.core_config.settings.PHOTON_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.PHOTON_API_HOST", "photon.komoot.io")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: False)
    @patch(f"{_SVC}.requests.get")
    def test_photon_no_features_returns_none(self, mock_get):
        mock_get.return_value.json.return_value = {"features": []}
        assert reverse_geocode(38.0, -9.0) is None

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "geocode")
    @patch(f"{_SVC}.core_config.settings.GEOCODES_MAPS_API", "valid_key")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}.requests.get")
    def test_geocode_success(self, mock_get):
        mock_get.return_value.json.return_value = {"address": {"city": "Lisbon", "country": "Portugal"}}
        result = reverse_geocode(38.0, -9.0)
        assert result == LocationResult(city="Lisbon", town=None, country="Portugal")

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: False)
    @patch(f"{_SVC}.requests.get")
    def test_http_error_returns_none(self, mock_get):
        mock_get.side_effect = Exception("Connection error")
        assert reverse_geocode(38.0, -9.0) is None

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_LOCK")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: False)
    @patch(f"{_SVC}.requests.get")
    @patch(f"{_SVC}.time.sleep")
    @patch(f"{_SVC}.time.monotonic")
    def test_rate_limiting_applied(self, mock_monotonic, mock_sleep, mock_get, mock_lock):
        with (
            patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 1),
            patch(f"{_SVC}.core_config.REVERSE_GEO_LAST_CALL", 0),
        ):
            mock_lock.__enter__.return_value = None
            mock_lock.__exit__.return_value = None
            mock_monotonic.side_effect = [0.5, 0.5]
            mock_get.return_value.json.return_value = {"address": {"country": "Test"}}

            result = reverse_geocode(0.0, 0.0)

            assert result is not None
            mock_sleep.assert_called_once()

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "nominatim.openstreetmap.org")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.core_config.API_VERSION", "1.0")
    @patch(f"{_SVC}.requests.get")
    def test_redirects_disabled(self, mock_get):
        """SSRF A10: the request must not follow provider redirects."""
        mock_get.return_value.json.return_value = {"address": {"country": "Test"}}
        reverse_geocode(38.0, -9.0)
        assert mock_get.call_args.kwargs["allow_redirects"] is False

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_USE_HTTPS", True)
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "http://evil.example.com/reverse?x=")
    @patch(f"{_SVC}.core_config.REVERSE_GEO_MIN_INTERVAL", 0)
    @patch(f"{_SVC}.requests.get")
    def test_invalid_host_is_rejected(self, mock_get):
        """SSRF A10: a host carrying a scheme/path is rejected without a request."""
        assert reverse_geocode(38.0, -9.0) is None
        mock_get.assert_not_called()

    @patch(f"{_SVC}.core_config.settings.REVERSE_GEO_PROVIDER", "nominatim")
    @patch(f"{_SVC}.core_config.settings.NOMINATIM_API_HOST", "nominatim.internal")
    @patch(f"{_SVC}._resolves_to_blocked_ip", lambda host: True)
    @patch(f"{_SVC}.requests.get")
    def test_nominatim_blocked_ip_skips_request(self, mock_get):
        """SSRF A10: a host resolving to a private/loopback IP is rejected without a request."""
        assert reverse_geocode(38.0, -9.0) is None
        mock_get.assert_not_called()


class TestIsValidHost:
    """The SSRF host allow-list predicate."""

    def test_accepts_bare_hosts(self):
        assert _is_valid_host("nominatim.openstreetmap.org")
        assert _is_valid_host("nominatim.local")
        assert _is_valid_host("nominatim:8080")
        assert _is_valid_host("192.168.1.10:8080")

    def test_rejects_ssrf_shapes(self):
        assert not _is_valid_host(None)
        assert not _is_valid_host("")
        assert not _is_valid_host("http://host")
        assert not _is_valid_host("host/reverse")
        assert not _is_valid_host("user@host")
        assert not _is_valid_host("host name")


class TestResolvesToBlockedIp:
    """The SSRF IP-range denylist (resolve + reject private/loopback/link-local)."""

    def test_none_host_is_blocked(self):
        assert _resolves_to_blocked_ip(None) is True

    @patch(f"{_SVC}.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.1", 0))])
    def test_private_ip_is_blocked(self, _gai):
        assert _resolves_to_blocked_ip("nominatim.internal") is True

    @patch(f"{_SVC}.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("169.254.169.254", 0))])
    def test_link_local_metadata_is_blocked(self, _gai):
        assert _resolves_to_blocked_ip("metadata") is True

    @patch(f"{_SVC}.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 0))])
    def test_loopback_is_blocked(self, _gai):
        assert _resolves_to_blocked_ip("localhost:8080") is True

    @patch(f"{_SVC}.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 0))])
    def test_public_ip_is_allowed(self, _gai):
        assert _resolves_to_blocked_ip("nominatim.openstreetmap.org") is False

    @patch(f"{_SVC}.socket.getaddrinfo", side_effect=OSError("nxdomain"))
    def test_unresolvable_host_is_blocked(self, _gai):
        assert _resolves_to_blocked_ip("does.not.exist") is True

    @patch(
        f"{_SVC}.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("8.8.8.8", 0)), (2, 1, 6, "", ("10.0.0.1", 0))],
    )
    def test_blocked_when_any_resolved_ip_is_private(self, _gai):
        assert _resolves_to_blocked_ip("mixed.example.com") is True


class TestGeocodeAndStore:
    """The create-path store helper."""

    @patch(f"{_SVC}.activity_streams_crud.get_activity_stream_by_type", return_value=None)
    @patch(f"{_SVC}.activities_crud.update_activity_location")
    def test_no_stream_returns_false(self, mock_update, _mock_stream):
        assert geocode_and_store_activity_location(1, 2, MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.reverse_geocode", return_value=None)
    @patch(f"{_SVC}.activity_streams_crud.get_activity_stream_by_type")
    @patch(f"{_SVC}.activities_crud.update_activity_location")
    def test_unresolved_location_returns_false(self, mock_update, mock_stream, _mock_geo):
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 1.0, "lon": 2.0}])
        assert geocode_and_store_activity_location(1, 2, MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.reverse_geocode", return_value=LocationResult("Lisbon", "Belem", "Portugal"))
    @patch(f"{_SVC}.activity_streams_crud.get_activity_stream_by_type")
    @patch(f"{_SVC}.activities_crud.update_activity_location")
    def test_success_stores_location(self, mock_update, mock_stream, _mock_geo):
        db = MagicMock()
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 38.0, "lon": -9.0}])
        assert geocode_and_store_activity_location(42, 7, db) is True
        mock_update.assert_called_once_with(42, "Lisbon", "Belem", "Portugal", db)


class TestBackfill:
    """The reconciliation backfill."""

    @patch(f"{_SVC}.activities_crud.get_activities_missing_location", return_value=[])
    def test_no_candidates_returns_zero(self, _mock_candidates):
        assert backfill_missing_activity_locations(MagicMock()) == 0

    @patch(f"{_SVC}.reverse_geocode", return_value=LocationResult("Lisbon", None, "Portugal"))
    @patch(f"{_SVC}.activity_streams_crud.get_gps_stream_waypoints_for_activities")
    @patch(f"{_SVC}.activities_crud.get_activities_missing_location")
    @patch(f"{_SVC}.activities_crud.update_activity_location")
    def test_stores_for_gps_candidates(self, mock_update, mock_candidates, mock_waypoints, _mock_geo):
        db = MagicMock()
        mock_candidates.return_value = [
            MagicMock(id=1),
            MagicMock(id=2),  # no GPS -> skipped
        ]
        mock_waypoints.return_value = {1: [{"lat": 38.0, "lon": -9.0}]}
        stored = backfill_missing_activity_locations(db)
        assert stored == 1
        mock_update.assert_called_once_with(1, "Lisbon", None, "Portugal", db)

    @patch(f"{_SVC}.reverse_geocode")
    @patch(f"{_SVC}.activity_streams_crud.get_gps_stream_waypoints_for_activities")
    @patch(f"{_SVC}.activities_crud.get_activities_missing_location")
    @patch(f"{_SVC}.activities_crud.update_activity_location")
    def test_skips_empty_waypoints(self, mock_update, mock_candidates, mock_waypoints, mock_geo):
        mock_candidates.return_value = [MagicMock(id=1)]
        mock_waypoints.return_value = {1: []}
        assert backfill_missing_activity_locations(MagicMock()) == 0
        mock_geo.assert_not_called()
        mock_update.assert_not_called()
