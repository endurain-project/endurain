"""Tests for the reverse-geocoding configuration and its mapping onto the substrate."""

import jasil.settings as jasil_settings
import pytest

import core.config as core_config
import core.geocoding as core_geocoding


def _config(**overrides) -> core_geocoding.GeocodingConfig:
    values = dict(
        service=core_geocoding.GeocodingService.NOMINATIM,
        host=None,
        use_https=True,
        rate_limit=1.0,
    )
    values.update(overrides)
    return core_geocoding.GeocodingConfig(**values)


class TestToGeocodingSettings:
    def test_none_is_unset(self):
        assert core_geocoding.to_geocoding_settings(None) == jasil_settings.GeocodingSettings()

    @pytest.mark.parametrize(
        ("service", "default_host"),
        [
            (core_geocoding.GeocodingService.NOMINATIM, "nominatim.openstreetmap.org"),
            (core_geocoding.GeocodingService.PHOTON, "photon.komoot.io"),
        ],
    )
    def test_no_host_means_the_default_host(self, service, default_host):
        result = core_geocoding.to_geocoding_settings(_config(service=service))

        assert result.uri == f"{service.value}://{default_host}"

    def test_hosts_and_rate_limit_are_mapped(self):
        config = _config(service=core_geocoding.GeocodingService.PHOTON, host="photon.example.com", rate_limit=2.5)

        result = core_geocoding.to_geocoding_settings(config)

        assert result.uri == "photon://photon.example.com"
        assert result.rate_limit == 2.5

    def test_cleartext_uses_the_http_scheme(self):
        result = core_geocoding.to_geocoding_settings(_config(host="nominatim.example.org:8080", use_https=False))

        assert result.uri == "nominatim+http://nominatim.example.org:8080"

    def test_geocode_ignores_the_host(self):
        config = _config(service=core_geocoding.GeocodingService.GEOCODE, host="ignored.example.com", api_key="k")

        result = core_geocoding.to_geocoding_settings(config)

        assert result.uri == "geocode://"
        assert result.api_key == "k"

    def test_user_agent_identifies_endurain(self):
        result = core_geocoding.to_geocoding_settings(_config())

        assert result.user_agent == f"Endurain/{core_config.API_VERSION} (ReverseGeocoding)"
