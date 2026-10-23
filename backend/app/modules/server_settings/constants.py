"""Constants for server settings."""

from typing import Any

#: Storage area and key of the custom login-page photo. The area matches the legacy
#: ``{DATA_DIR}/server_images`` directory, so a photo uploaded before the
#: ``StorageProvider`` is found by the local backend without migrating it.
LOGIN_PHOTO_STORAGE_AREA = "server_images"
LOGIN_PHOTO_STORAGE_KEY = "login.png"

#: Largest accepted login-photo upload, in bytes. The login page shows it full-bleed to
#: every anonymous visitor, so it is capped well below the generic image upload limit.
LOGIN_PHOTO_MAX_BYTES = 5 * 1024 * 1024

#: The tile source a fresh install starts with, and the built-in OpenStreetMap preset.
DEFAULT_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

#: Tile domains the CSP ``img-src`` directive always allows.
DEFAULT_ALLOWED_TILE_DOMAINS: list[str] = [
    "https://*.openstreetmap.org",  # OpenStreetMap
    "https://*.stadiamaps.com",  # Stadia Maps
]

#: Mail settings field -> the deprecated environment variable that sets it. The mail block is
#: imported as a whole, so all of these are env-managed while ``SMTP_HOST`` is set.
MAIL_ENV_VARS: dict[str, str] = {
    "host": "SMTP_HOST",
    "port": "SMTP_PORT",
    "security": "SMTP_SECURE",
    "username": "SMTP_USERNAME",
    "password": "SMTP_PASSWORD",
    "from_address": "SMTP_FROM",
}

#: Geocoding field -> the deprecated environment variable that sets it (the Nominatim variant
#: for the per-service host and HTTPS fields). The block is imported as a whole, so all of
#: these are env-managed while any variable in ``GEOCODING_ENV_VAR_NAMES`` is set.
GEOCODING_ENV_VARS: dict[str, str] = {
    "geocoding_service": "REVERSE_GEO_PROVIDER",
    "geocoding_host": "NOMINATIM_API_HOST",
    "geocoding_use_https": "NOMINATIM_API_USE_HTTPS",
    "geocoding_rate_limit": "REVERSE_GEO_RATE_LIMIT",
    "geocoding_api_key": "GEOCODES_MAPS_API",
}

#: The Photon variants of the per-service geocoding fields.
GEOCODING_PHOTON_ENV_VARS: dict[str, str] = {
    "geocoding_host": "PHOTON_API_HOST",
    "geocoding_use_https": "PHOTON_API_USE_HTTPS",
}

#: Every deprecated geocoding variable; any one of them being set makes the block env-managed.
GEOCODING_ENV_VAR_NAMES: tuple[str, ...] = (*GEOCODING_ENV_VARS.values(), *GEOCODING_PHOTON_ENV_VARS.values())

#: Session policy field -> the deprecated environment variable that sets it. Each variable
#: makes only its own field env-managed.
SESSION_ENV_VARS: dict[str, str] = {
    "session_idle_timeout_enabled": "SESSION_IDLE_TIMEOUT_ENABLED",
    "session_idle_timeout_hours": "SESSION_IDLE_TIMEOUT_HOURS",
    "session_absolute_timeout_hours": "SESSION_ABSOLUTE_TIMEOUT_HOURS",
    "access_token_expire_minutes": "ACCESS_TOKEN_EXPIRE_MINUTES",
    "refresh_token_expire_days": "REFRESH_TOKEN_EXPIRE_DAYS",
}

#: Read-notification retention field -> the deprecated environment variable that sets it.
RETENTION_ENV_VARS: dict[str, str] = {"read_notification_retention_days": "READ_NOTIFICATION_RETENTION_DAYS"}

#: Logged once at boot when deprecated environment variables were found; ``{names}`` is
#: the comma-separated variable names, never their values.
DEPRECATED_ENV_WARNING = (
    "The environment variables {names} are deprecated. Their values were saved to the "
    "database and are now edited in Settings > Server. Remove them from your "
    "environment: while they are set they overwrite the stored values on every start, "
    "and from v0.22.0 Endurain refuses to start while any of them is set."
)

TILE_MAPS_TEMPLATES: dict[str, dict[str, Any]] = {
    "openstreetmap": {
        "name": "OpenStreetMap",
        "url_template": DEFAULT_TILE_URL,
        "attribution": DEFAULT_TILE_ATTRIBUTION,
        "map_background_color": "#e8e8e8",
        "requires_api_key_frontend": False,
        "requires_api_key_backend": False,
    },
    "alidade_smooth": {
        "name": "Stadia Maps Alidade Smooth",
        "url_template": "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png",
        "attribution": '&copy; <a href="https://stadiamaps.com/" target="_blank">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
        "map_background_color": "#f5f5f5",
        "requires_api_key_frontend": False,
        "requires_api_key_backend": True,
    },
    "alidade_smooth_dark": {
        "name": "Stadia Maps Alidade Smooth Dark",
        "url_template": "https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}{r}.png",
        "attribution": '&copy; <a href="https://stadiamaps.com/" target="_blank">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
        "map_background_color": "#2a2a2a",
        "requires_api_key_frontend": False,
        "requires_api_key_backend": True,
    },
    "alidade_satellite": {
        "name": "Stadia Maps Alidade Satellite",
        "url_template": "https://tiles.stadiamaps.com/tiles/alidade_satellite/{z}/{x}/{y}.jpg",
        "attribution": '&copy; CNES, Distribution Airbus DS, &copy; Airbus DS, &copy; PlanetObserver (Contains Copernicus Data) | &copy; <a href="https://stadiamaps.com/" target="_blank">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
        "map_background_color": "#1a1a1a",
        "requires_api_key_frontend": True,
        "requires_api_key_backend": True,
    },
    "stadia_outdoors": {
        "name": "Stadia Maps Outdoors",
        "url_template": "https://tiles.stadiamaps.com/tiles/outdoors/{z}/{x}/{y}{r}.png",
        "attribution": '&copy; <a href="https://stadiamaps.com/" target="_blank">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/" target="_blank">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
        "map_background_color": "#e0e0e0",
        "requires_api_key_frontend": False,
        "requires_api_key_backend": True,
    },
}
