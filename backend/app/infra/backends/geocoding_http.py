"""HTTP ``GeocodingProvider`` backends (Nominatim / Photon / geocode.maps.co).

One class covers all three services because they differ only in how the request
URL is built and how the answer is shaped; everything that actually matters —
egress validation, redirect refusal, rate limiting, and never raising — is
identical and is written once here.

Security (OWASP A10 — SSRF): the upstream host is operator-configured, so it is
validated through :func:`core.network.host_rejection_reason` — the same address
denylist and ``SSRF_ALLOWED_HOSTS`` allowlist the OIDC client uses — before the
first request, and redirects are refused on every request so a permitted host
cannot 3xx-pivot onto an internal target.
"""

import threading
import time
from urllib.parse import urlencode

import requests

import core.logger as core_logger
import core.network as core_network
from infra.providers import GeocodedPlace

logger = core_logger.get_logger(__name__)

# Egress timeout for a single reverse-geocode request (seconds).
_TIMEOUT_SECONDS = 10


class NullGeocoding:
    """``GeocodingProvider`` that resolves nothing.

    Selected when reverse geocoding is not configured, is configured with an
    unsupported provider, or is configured with a host that fails egress
    validation. Making "disabled" an explicit backend means the domain has one
    code path: it always has a provider and always just calls it.
    """

    def reverse(self, latitude: float, longitude: float) -> GeocodedPlace | None:
        """Return ``None`` — no geocoding is configured."""
        return None


class HttpGeocoding:
    """``GeocodingProvider`` backed by a reverse-geocoding HTTP service.

    Args:
        service: Which upstream to call — ``"nominatim"``, ``"photon"`` or
            ``"geocode"``.
        base_url: Fully-qualified reverse endpoint, e.g.
            ``"https://nominatim.openstreetmap.org/reverse"``. Built by the
            composition root, which is also where the host was validated.
        api_key: API key, for the services that require one (geocode.maps.co).
        min_interval_seconds: Minimum wall-clock gap between requests. ``0``
            disables throttling.
        user_agent: ``User-Agent`` sent upstream; Nominatim's usage policy
            requires an identifying value.
    """

    def __init__(
        self,
        service: str,
        base_url: str,
        *,
        api_key: str | None = None,
        min_interval_seconds: float = 0.0,
        user_agent: str = "Endurain (ReverseGeocoding)",
    ) -> None:
        self._service = service
        self._base_url = base_url
        self._api_key = api_key
        self._min_interval = min_interval_seconds
        self._user_agent = user_agent
        # Throttle state is per-instance, guarded by its own lock. It used to be
        # three module-level globals in core.config mutated from the domain
        # service, which made the rate limit both untestable and impossible to
        # reason about with more than one caller.
        self._throttle_lock = threading.Lock()
        self._last_call = 0.0

    def _build_url(self, latitude: float, longitude: float) -> str:
        """Build the reverse-geocode URL for the configured service."""
        if self._service == "photon":
            params = {"lat": latitude, "lon": longitude}
        elif self._service == "geocode":
            params = {"lat": latitude, "lon": longitude, "api_key": self._api_key}
        else:  # nominatim
            params = {"format": "jsonv2", "lat": latitude, "lon": longitude}
        return f"{self._base_url}?{urlencode(params)}"

    def _parse(self, payload: dict) -> GeocodedPlace | None:
        """Extract city/town/country from a service response, or None when empty."""
        if self._service == "photon":
            # Photon uses 'district' for city and 'city' for town.
            features = payload.get("features", [])
            data = features[0].get("properties", {}) if features else {}
            city = data.get("district")
            town = data.get("city")
        else:
            # Nominatim and geocode.maps.co share a shape; 'town' is the district.
            data = payload.get("address", {})
            city = data.get("city")
            town = data.get("town")
        country = data.get("country")

        if not any((city, town, country)):
            return None
        return GeocodedPlace(city=city, town=town, country=country)

    def _throttle(self) -> None:
        """Sleep as needed to respect the configured request rate."""
        if self._min_interval <= 0:
            return
        with self._throttle_lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def reverse(self, latitude: float, longitude: float) -> GeocodedPlace | None:
        """Reverse-geocode a coordinate, returning ``None`` on any failure.

        Args:
            latitude: WGS-84 latitude in decimal degrees.
            longitude: WGS-84 longitude in decimal degrees.

        Returns:
            The resolved place, or ``None`` when nothing resolved or the request
            failed. Never raises — geocoding is best-effort enrichment and must
            not fail the import or backfill that triggered it.
        """
        logger.debug(f"Reverse-geocoding ({latitude}, {longitude}) via {self._service}")
        self._throttle()
        try:
            response = requests.get(
                self._build_url(latitude, longitude),
                headers={"User-Agent": self._user_agent},
                timeout=_TIMEOUT_SECONDS,
                # A permitted host must not 3xx-pivot the request onto an
                # internal target (SSRF defense in depth, OWASP A10).
                allow_redirects=False,
            )
            response.raise_for_status()
            return self._parse(response.json())
        except Exception as err:
            logger.error(
                f"Reverse-geocoding via {self._service} failed - {err}",
                extra=core_logger.context(console=True),
            )
            return None


def build_reverse_endpoint(host: str, *, use_https: bool) -> str | None:
    """Validate an operator-configured host and build its reverse endpoint URL.

    Args:
        host: The configured bare ``host[:port]`` authority.
        use_https: Whether to address the host over HTTPS.

    Returns:
        The ``{scheme}://{host}/reverse`` URL, or ``None`` when the host failed
        SSRF validation (the reason is logged). A self-hosted instance on a
        private network is reachable by adding it to ``SSRF_ALLOWED_HOSTS``,
        which this check honours.
    """
    reason = core_network.host_rejection_reason(host, purpose="reverse_geocoding")
    if reason is not None:
        logger.warning(
            f"Reverse-geocoding host {host!r} {reason}; reverse geocoding is disabled "
            "and activities will have no location. A self-hosted instance on a private "
            "network must be allow-listed via SSRF_ALLOWED_HOSTS.",
            extra=core_logger.context(console=True),
        )
        return None
    scheme = "https" if use_https else "http"
    return f"{scheme}://{host}/reverse"
