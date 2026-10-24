"""Operator-edited reverse-geocoding configuration and its mapping onto the substrate.

The substrate reloads its geocoding backend from these settings at runtime, so there
is no provider class here; this module owns the configuration shape and the mapping.
"""

import dataclasses
from enum import StrEnum
from typing import Final

import jasil.settings as jasil_settings

import core.config as core_config


class GeocodingService(StrEnum):
    """The reverse-geocoding service in use.

    Attributes:
        NOMINATIM: A Nominatim instance, the public one by default.
        PHOTON: A Photon instance, the public one by default.
        GEOCODE: geocode.maps.co, a fixed host that needs an API key.
    """

    NOMINATIM = "nominatim"
    PHOTON = "photon"
    GEOCODE = "geocode"


#: The public host each self-hostable service uses when none is configured.
DEFAULT_HOSTS: Final = {
    GeocodingService.NOMINATIM: "nominatim.openstreetmap.org",
    GeocodingService.PHOTON: "photon.komoot.io",
}


@dataclasses.dataclass(frozen=True)
class GeocodingConfig:
    """The decrypted, ready-to-use reverse-geocoding configuration.

    Attributes:
        service: The geocoding service.
        host: Host (and optional port) of the service, or None for its default host;
            ignored for geocode.maps.co.
        use_https: Whether to address the host over HTTPS.
        rate_limit: Maximum requests per second; 0 disables throttling.
        api_key: API key in plain text, or None.
    """

    service: GeocodingService
    host: str | None
    use_https: bool
    rate_limit: float
    api_key: str | None = dataclasses.field(default=None, repr=False)


def to_geocoding_settings(config: GeocodingConfig | None) -> jasil_settings.GeocodingSettings:
    """Map a geocoding configuration onto the substrate's geocoding settings.

    No validation happens here; the substrate validates what it is given and disables
    geocoding, logging why, when the settings are unusable.

    Args:
        config: The geocoding configuration, or None when geocoding is unavailable.

    Returns:
        The equivalent settings; unset (geocoding disabled) when ``config`` is None.
    """
    if config is None:
        return jasil_settings.GeocodingSettings()
    if config.service == GeocodingService.GEOCODE:
        uri = "geocode://"
    else:
        scheme = config.service.value if config.use_https else f"{config.service.value}+http"
        uri = f"{scheme}://{config.host or DEFAULT_HOSTS[config.service]}"
    return jasil_settings.GeocodingSettings(
        uri=uri,
        rate_limit=config.rate_limit,
        api_key=config.api_key,
        user_agent=f"Endurain/{core_config.API_VERSION} (ReverseGeocoding)",
    )
