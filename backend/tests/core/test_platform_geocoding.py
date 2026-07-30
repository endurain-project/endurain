"""Tests for the geocoding provider: HTTP backend and container wiring.

These moved out of ``tests/activities/activity_geocoding/test_service.py`` when
reverse geocoding became a platform provider — the upstream-service knowledge is
no longer a fact about activities. The SSRF host checks are *not* retested here:
they are ``core.network``'s, shared with the OIDC client, and covered in
``tests/core/test_network.py``.
"""

from unittest.mock import MagicMock, patch

import infra.backends.geocoding_http as geocoding_http
import infra.container as container
from infra.providers import GeocodedPlace, GeocodingProvider

_BACKEND = "infra.backends.geocoding_http"


class TestBuildReverseEndpoint:
    def test_builds_https_endpoint_for_a_safe_host(self):
        with patch(f"{_BACKEND}.core_network.host_rejection_reason", return_value=None):
            url = geocoding_http.build_reverse_endpoint("nominatim.openstreetmap.org", use_https=True)
        assert url == "https://nominatim.openstreetmap.org/reverse"

    def test_builds_http_endpoint_when_https_is_disabled(self):
        with patch(f"{_BACKEND}.core_network.host_rejection_reason", return_value=None):
            url = geocoding_http.build_reverse_endpoint("nominatim.local", use_https=False)
        assert url == "http://nominatim.local/reverse"

    def test_returns_none_for_a_rejected_host(self):
        with patch(
            f"{_BACKEND}.core_network.host_rejection_reason", return_value="is not a bare host[:port] authority"
        ):
            assert geocoding_http.build_reverse_endpoint("http://evil.example.com/x", use_https=True) is None

    def test_passes_a_purpose_for_the_ssrf_audit_log(self):
        with patch(f"{_BACKEND}.core_network.host_rejection_reason", return_value=None) as check:
            geocoding_http.build_reverse_endpoint("nominatim.local", use_https=False)
        assert check.call_args.kwargs["purpose"] == "reverse_geocoding"


class TestNullGeocoding:
    def test_resolves_nothing(self):
        assert geocoding_http.NullGeocoding().reverse(38.0, -9.0) is None

    def test_satisfies_the_provider_protocol(self):
        assert isinstance(geocoding_http.NullGeocoding(), GeocodingProvider)


class TestHttpGeocoding:
    """URL building, response parsing, and the never-raise contract."""

    def _backend(self, service: str, base_url: str = "https://example.test/reverse", **kwargs):
        return geocoding_http.HttpGeocoding(service, base_url, **kwargs)

    @patch(f"{_BACKEND}.requests.get")
    def test_nominatim_success(self, mock_get):
        mock_get.return_value.json.return_value = {
            "address": {"city": "Lisbon", "town": "Belem", "country": "Portugal"}
        }
        result = self._backend("nominatim").reverse(38.0, -9.0)
        assert result == GeocodedPlace(city="Lisbon", town="Belem", country="Portugal")

    @patch(f"{_BACKEND}.requests.get")
    def test_nominatim_requests_jsonv2(self, mock_get):
        mock_get.return_value.json.return_value = {"address": {"country": "Portugal"}}
        self._backend("nominatim").reverse(38.0, -9.0)
        assert "format=jsonv2" in mock_get.call_args.args[0]

    @patch(f"{_BACKEND}.requests.get")
    def test_nominatim_empty_address_returns_none(self, mock_get):
        mock_get.return_value.json.return_value = {"address": {}}
        assert self._backend("nominatim").reverse(38.0, -9.0) is None

    @patch(f"{_BACKEND}.requests.get")
    def test_photon_success(self, mock_get):
        # Photon uses 'district' for city and 'city' for town.
        mock_get.return_value.json.return_value = {
            "features": [{"properties": {"district": "Lisbon", "city": "Belem", "country": "Portugal"}}]
        }
        result = self._backend("photon").reverse(38.0, -9.0)
        assert result == GeocodedPlace(city="Lisbon", town="Belem", country="Portugal")

    @patch(f"{_BACKEND}.requests.get")
    def test_photon_no_features_returns_none(self, mock_get):
        mock_get.return_value.json.return_value = {"features": []}
        assert self._backend("photon").reverse(38.0, -9.0) is None

    @patch(f"{_BACKEND}.requests.get")
    def test_geocode_sends_the_api_key(self, mock_get):
        mock_get.return_value.json.return_value = {"address": {"city": "Lisbon", "country": "Portugal"}}
        result = self._backend("geocode", api_key="secret-key").reverse(38.0, -9.0)
        assert result == GeocodedPlace(city="Lisbon", town=None, country="Portugal")
        assert "api_key=secret-key" in mock_get.call_args.args[0]

    @patch(f"{_BACKEND}.requests.get")
    def test_redirects_disabled(self, mock_get):
        """SSRF A10: a permitted host must not 3xx-pivot onto an internal target."""
        mock_get.return_value.json.return_value = {"address": {"country": "Test"}}
        self._backend("nominatim").reverse(38.0, -9.0)
        assert mock_get.call_args.kwargs["allow_redirects"] is False

    @patch(f"{_BACKEND}.requests.get")
    def test_sends_an_identifying_user_agent(self, mock_get):
        # Nominatim's usage policy requires it.
        mock_get.return_value.json.return_value = {"address": {"country": "Test"}}
        self._backend("nominatim", user_agent="Endurain/1.0 (ReverseGeocoding)").reverse(38.0, -9.0)
        assert mock_get.call_args.kwargs["headers"]["User-Agent"] == "Endurain/1.0 (ReverseGeocoding)"

    @patch(f"{_BACKEND}.requests.get", side_effect=Exception("Connection error"))
    def test_upstream_failure_returns_none_and_never_raises(self, _mock_get):
        # The provider contract: geocoding must not fail the import that ran it.
        assert self._backend("nominatim").reverse(38.0, -9.0) is None

    @patch(f"{_BACKEND}.requests.get")
    def test_http_error_returns_none(self, mock_get):
        mock_get.return_value.raise_for_status.side_effect = Exception("503")
        assert self._backend("nominatim").reverse(38.0, -9.0) is None

    @patch(f"{_BACKEND}.time.sleep")
    @patch(f"{_BACKEND}.requests.get")
    def test_no_sleep_when_throttling_is_disabled(self, mock_get, mock_sleep):
        mock_get.return_value.json.return_value = {"address": {"country": "Test"}}
        self._backend("nominatim", min_interval_seconds=0).reverse(38.0, -9.0)
        mock_sleep.assert_not_called()

    @patch(f"{_BACKEND}.time.sleep")
    @patch(f"{_BACKEND}.requests.get")
    def test_second_call_waits_for_the_configured_interval(self, mock_get, mock_sleep):
        mock_get.return_value.json.return_value = {"address": {"country": "Test"}}
        backend = self._backend("nominatim", min_interval_seconds=1)

        backend.reverse(38.0, -9.0)
        backend.reverse(38.0, -9.0)

        # First call has no predecessor to wait for; the second does.
        mock_sleep.assert_called_once()
        assert 0 < mock_sleep.call_args.args[0] <= 1


class TestBuildGeocoding:
    """The composition root's backend selection."""

    def _settings(self, **overrides):
        settings = MagicMock()
        settings.REVERSE_GEO_RATE_LIMIT = 1.0
        settings.REVERSE_GEO_PROVIDER = "nominatim"
        settings.NOMINATIM_API_HOST = "nominatim.openstreetmap.org"
        settings.NOMINATIM_API_USE_HTTPS = True
        settings.PHOTON_API_HOST = "photon.komoot.io"
        settings.PHOTON_API_USE_HTTPS = True
        settings.GEOCODES_MAPS_API = "changeme"
        for key, value in overrides.items():
            setattr(settings, key, value)
        return settings

    def test_unsupported_provider_disables_geocoding(self):
        result = container._build_geocoding(self._settings(REVERSE_GEO_PROVIDER="unsupported"))
        assert isinstance(result, geocoding_http.NullGeocoding)

    def test_geocode_without_an_api_key_disables_geocoding(self):
        result = container._build_geocoding(self._settings(REVERSE_GEO_PROVIDER="geocode"))
        assert isinstance(result, geocoding_http.NullGeocoding)

    def test_geocode_with_an_api_key_is_enabled(self):
        result = container._build_geocoding(
            self._settings(REVERSE_GEO_PROVIDER="geocode", GEOCODES_MAPS_API="real-key")
        )
        assert isinstance(result, geocoding_http.HttpGeocoding)

    def test_a_rejected_host_disables_geocoding_rather_than_failing_startup(self):
        # Geocoding is optional enrichment: a bad host must not stop the app.
        result = container._build_geocoding(self._settings(NOMINATIM_API_HOST="http://evil.example.com/x"))
        assert isinstance(result, geocoding_http.NullGeocoding)

    def test_a_safe_nominatim_host_is_enabled(self):
        with patch(f"{_BACKEND}.core_network.host_rejection_reason", return_value=None):
            result = container._build_geocoding(self._settings())
        assert isinstance(result, geocoding_http.HttpGeocoding)

    def test_a_safe_photon_host_is_enabled(self):
        with patch(f"{_BACKEND}.core_network.host_rejection_reason", return_value=None):
            result = container._build_geocoding(self._settings(REVERSE_GEO_PROVIDER="photon"))
        assert isinstance(result, geocoding_http.HttpGeocoding)

    def test_zero_rate_limit_disables_throttling(self):
        with patch(f"{_BACKEND}.core_network.host_rejection_reason", return_value=None):
            result = container._build_geocoding(self._settings(REVERSE_GEO_RATE_LIMIT=0))
        assert result._min_interval == 0.0


class TestBuildGeocodingDiagnostics:
    """Every outcome must be explainable from the startup log.

    A disabled geocoding capability is otherwise invisible: activities simply
    have no city/town/country and nothing says why. These assert the operator
    always gets a line, including on success.
    """

    def _settings(self, **overrides):
        return TestBuildGeocoding()._settings(**overrides)

    def test_unsupported_provider_is_warned_with_the_valid_options(self):
        with patch.object(container, "logger") as mock_log:
            container._build_geocoding(self._settings(REVERSE_GEO_PROVIDER="nominatm"))
        message = mock_log.warning.call_args[0][0]
        assert "nominatm" in message
        assert "nominatim" in message and "photon" in message and "geocode" in message

    def test_placeholder_api_key_is_warned_by_name(self):
        with patch.object(container, "logger") as mock_log:
            container._build_geocoding(self._settings(REVERSE_GEO_PROVIDER="geocode"))
        message = mock_log.warning.call_args[0][0]
        assert "GEOCODES_MAPS_API" in message
        assert "changeme" in message

    def test_rejected_host_is_warned_with_the_reason_and_the_remedy(self):
        with patch.object(geocoding_http, "logger") as mock_log:
            container._build_geocoding(self._settings(NOMINATIM_API_HOST="http://evil.example.com/x"))
        message = mock_log.warning.call_args[0][0]
        assert "bare host" in message
        assert "SSRF_ALLOWED_HOSTS" in message

    def test_every_disabled_path_says_locations_will_be_missing(self):
        cases = [
            (container, {"REVERSE_GEO_PROVIDER": "nope"}),
            (container, {"REVERSE_GEO_PROVIDER": "geocode"}),
            (geocoding_http, {"NOMINATIM_API_HOST": "http://evil.example.com/x"}),
        ]
        for module, overrides in cases:
            with patch.object(module, "logger") as mock_log:
                container._build_geocoding(self._settings(**overrides))
            assert "no location" in mock_log.warning.call_args[0][0]

    def test_success_is_logged_with_the_resolved_endpoint(self):
        with (
            patch(f"{_BACKEND}.core_network.host_rejection_reason", return_value=None),
            patch.object(container, "logger") as mock_log,
        ):
            container._build_geocoding(self._settings())
        message = mock_log.info.call_args[0][0]
        assert "enabled" in message
        assert "https://nominatim.openstreetmap.org/reverse" in message

    def test_diagnostics_are_mirrored_to_the_console(self):
        # Startup configuration problems follow the same convention as the rest
        # of the boot sequence, so they are visible when running locally.
        with patch.object(container, "logger") as mock_log:
            container._build_geocoding(self._settings(REVERSE_GEO_PROVIDER="nope"))
        assert mock_log.warning.call_args.kwargs["extra"]["console"] is True
