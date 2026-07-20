"""Reverse-geocode activity locations off the ingestion path.

Owns the network reverse-geocoding that used to run inline inside the file
parsers (module rework plan §6.2 / A4d). Parsers now emit an activity with no
``city``/``town``/``country``; the ``activity.created`` subscriber calls in here to
resolve and persist the location, and the scheduled backfill re-resolves any that
were missed. Being a subscriber (not part of parsing) keeps the parse path free of
network I/O and lets the work run durably/async when durable jobs are enabled.

Security (OWASP A10 — SSRF): the provider host is operator-configured, so this
module validates it is a bare ``host[:port]`` authority (no scheme, path, or
credentials) and disables HTTP redirects, so a misconfigured or compromised
provider cannot pivot the request onto an internal target.
"""

import re
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from sqlalchemy.orm import Session

import core.config as core_config
import core.logger as core_logger
import modules.activities.activity.crud as activities_crud
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.crud as activity_streams_crud

# Egress timeout for a single reverse-geocode request (seconds).
_GEOCODE_TIMEOUT_SECONDS = 10

# A valid bare authority: hostname labels plus an optional ``:port``. Rejects any
# value carrying a scheme (``http://``), a path (``/reverse``), credentials
# (``user@host``), or whitespace — the SSRF-relevant shapes (OWASP A10).
_HOST_RE = re.compile(r"^[a-z0-9.\-]+(:[0-9]{1,5})?$")


@dataclass(frozen=True)
class LocationResult:
    """A resolved reverse-geocoded location (any field may be ``None``)."""

    city: str | None
    town: str | None
    country: str | None


def _is_valid_host(host: str | None) -> bool:
    """Return True when ``host`` is a bare ``host[:port]`` authority (SSRF guard)."""
    return host is not None and _HOST_RE.match(host) is not None


def _build_geocode_request(latitude: float, longitude: float) -> tuple[str, str] | None:
    """Build the ``(url, provider)`` for the configured provider, or None to skip.

    Validates the operator-configured host (SSRF, OWASP A10) and returns None when
    no provider is configured, the host is invalid, or the geocode.maps.co API key
    is still the ``changeme`` placeholder.

    Args:
        latitude: WGS-84 latitude in decimal degrees.
        longitude: WGS-84 longitude in decimal degrees.

    Returns:
        A ``(url, provider)`` tuple, or None when geocoding should be skipped.
    """
    provider = core_config.settings.REVERSE_GEO_PROVIDER
    if provider == "nominatim":
        host = core_config.settings.NOMINATIM_API_HOST
        if not _is_valid_host(host):
            core_logger.print_to_log(
                f"Invalid NOMINATIM_API_HOST {host!r}; skipping reverse-geocoding",
                "warning",
            )
            return None
        protocol = "https" if core_config.settings.NOMINATIM_API_USE_HTTPS else "http"
        params = urlencode({"format": "jsonv2", "lat": latitude, "lon": longitude})
        return f"{protocol}://{host}/reverse?{params}", provider
    if provider == "photon":
        host = core_config.settings.PHOTON_API_HOST
        if not _is_valid_host(host):
            core_logger.print_to_log(
                f"Invalid PHOTON_API_HOST {host!r}; skipping reverse-geocoding",
                "warning",
            )
            return None
        protocol = "https" if core_config.settings.PHOTON_API_USE_HTTPS else "http"
        params = urlencode({"lat": latitude, "lon": longitude})
        return f"{protocol}://{host}/reverse?{params}", provider
    if provider == "geocode":
        if core_config.settings.GEOCODES_MAPS_API == "changeme":
            return None
        params = urlencode(
            {
                "lat": latitude,
                "lon": longitude,
                "api_key": core_config.settings.GEOCODES_MAPS_API,
            }
        )
        return f"https://geocode.maps.co/reverse?{params}", provider
    return None


def _parse_geocode_response(provider: str, payload: dict) -> LocationResult | None:
    """Extract city/town/country from a provider response, or None when empty.

    Args:
        provider: The reverse-geocode provider the payload came from.
        payload: The decoded JSON response body.

    Returns:
        A :class:`LocationResult` when at least one field resolved, else None.
    """
    if provider in ("geocode", "nominatim"):
        # Note: 'town' is used for district in the Geocode API.
        data = payload.get("address", {})
        city = data.get("city")
        town = data.get("town")
        country = data.get("country")
    else:  # photon
        # Note: Photon uses 'district' for city and 'city' for town.
        features = payload.get("features", [])
        data = features[0].get("properties", {}) if features else {}
        city = data.get("district")
        town = data.get("city")
        country = data.get("country")

    if any([city, town, country]):
        return LocationResult(city=city, town=town, country=country)
    return None


def _throttle() -> None:
    """Respect the configured provider rate limit (process-wide throttle)."""
    if core_config.REVERSE_GEO_MIN_INTERVAL > 0:
        with core_config.REVERSE_GEO_LOCK:
            now = time.monotonic()
            interval = core_config.REVERSE_GEO_MIN_INTERVAL - (now - core_config.REVERSE_GEO_LAST_CALL)
            if interval > 0:
                time.sleep(interval)
            core_config.REVERSE_GEO_LAST_CALL = time.monotonic()


def reverse_geocode(latitude: float | None, longitude: float | None) -> LocationResult | None:
    """Reverse-geocode a ``(lat, lon)`` pair into a :class:`LocationResult`.

    Args:
        latitude: Latitude in decimal degrees, or None.
        longitude: Longitude in decimal degrees, or None.

    Returns:
        A :class:`LocationResult` with ``city``/``town``/``country`` (any may be
        None), or None when coordinates are missing, no provider is configured,
        the host is invalid, or the provider returns nothing / errors.
    """
    if latitude is None or longitude is None:
        return None

    built = _build_geocode_request(latitude, longitude)
    if built is None:
        return None
    url, provider = built

    core_logger.print_to_log(
        f"Reverse-geocoding ({latitude}, {longitude}) via {provider}",
        "debug",
    )

    _throttle()

    try:
        headers = {"User-Agent": f"Endurain/{core_config.API_VERSION} (ReverseGeocoding)"}
        # allow_redirects=False: an allow-listed provider must not 3xx-pivot the
        # request onto an internal host (SSRF defense in depth, OWASP A10).
        response = requests.get(
            url,
            headers=headers,
            timeout=_GEOCODE_TIMEOUT_SECONDS,
            allow_redirects=False,
        )
        response.raise_for_status()
        return _parse_geocode_response(provider, response.json())
    except Exception as err:
        # Log and return None so a geocoding failure never aborts the caller
        # (activity import / backfill); the backfill retries later.
        core_logger.print_to_log_and_console(f"Error in reverse_geocode - {err}", "error")
        return None


def geocode_and_store_activity_location(activity_id: int, user_id: int, db: Session) -> bool:
    """Resolve and persist a created activity's location from its GPS stream.

    Loads the activity's first GPS waypoint, reverse-geocodes it, and writes
    ``city``/``town``/``country`` back to the row. No-ops for non-GPS activities
    (no map stream) or when nothing resolves.

    Args:
        activity_id: The activity to geocode.
        user_id: The owning user (used to load the activity's own map stream).
        db: Database session.

    Returns:
        True when a location was resolved and stored, else False.
    """
    stream = activity_streams_crud.get_activity_stream_by_type(
        activity_id,
        activity_streams_constants.STREAM_TYPE_MAP,
        user_id,
        db,
    )
    if stream is None or not stream.stream_waypoints:
        return False

    first_waypoint = stream.stream_waypoints[0]
    location = reverse_geocode(first_waypoint.get("lat"), first_waypoint.get("lon"))
    if location is None:
        return False

    activities_crud.update_activity_location(
        activity_id,
        location.city,
        location.town,
        location.country,
        db,
    )
    core_logger.print_to_log(
        f"Stored location for activity {activity_id}: {location.city} / {location.town} / {location.country}",
        "debug",
    )
    return True


def backfill_missing_activity_locations(db: Session) -> int:
    """Resolve locations for GPS activities that still have none.

    Reconciliation net for the ``activity.created`` geocoding subscriber: it lists
    activities with an all-NULL location (bounded per pass), fetches their GPS
    waypoints in one batch, and reverse-geocodes each. Activities without a GPS
    stream are skipped.

    Args:
        db: Database session.

    Returns:
        The number of activities whose location was resolved and stored.
    """
    candidates = activities_crud.get_activities_missing_location(db)
    if not candidates:
        core_logger.print_to_log("Geocoding scheduler: no activities missing location", "debug")
        return 0

    candidate_ids = [ref.id for ref in candidates]
    waypoints_by_activity = activity_streams_crud.get_gps_stream_waypoints_for_activities(candidate_ids, db)

    stored = 0
    for activity_id, waypoints in waypoints_by_activity.items():
        if not waypoints:
            continue
        first_waypoint = waypoints[0]
        location = reverse_geocode(first_waypoint.get("lat"), first_waypoint.get("lon"))
        if location is None:
            continue
        activities_crud.update_activity_location(
            activity_id,
            location.city,
            location.town,
            location.country,
            db,
        )
        stored += 1

    core_logger.print_to_log(
        f"Geocoding scheduler: stored location for {stored} activity(ies) "
        f"out of {len(waypoints_by_activity)} GPS candidate(s)",
        "info" if stored else "debug",
    )
    return stored
