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
