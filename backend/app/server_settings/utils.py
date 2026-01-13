from urllib.parse import urlparse
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.logger as core_logger

import server_settings.crud as server_settings_crud
import server_settings.models as server_settings_models
import server_settings.schema as server_settings_schema


TILE_MAPS_TEMPLATES = {
    "openstreetmap": {
        "name": "OpenStreetMap",
        "url_template": "https://{s}.tile.openstreetmap.org/" "{z}/{x}/{y}.png",
        "attribution": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
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


def get_server_settings(db: Session) -> server_settings_models.ServerSettings:
    """
    Get server settings or raise 404.

    Args:
        db: Database session.

    Returns:
        ServerSettings instance.

    Raises:
        HTTPException: If server settings not found.
    """
    server_settings = server_settings_crud.get_server_settings(db)

    if not server_settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server settings not found",
        ) from None

    return server_settings


def get_server_settings_for_admin(
    db: Session,
) -> server_settings_schema.ServerSettingsRead:
    """
    Get server settings with decrypted API key for admin access.

    This function retrieves server settings and decrypts the tileserver
    API key for admin users who need to view the actual key value.

    Args:
        db: Database session.

    Returns:
        ServerSettingsRead schema with decrypted API key.

    Raises:
        HTTPException: If server settings not found.
    """
    server_settings = get_server_settings(db)

    # Decrypt the API key if it exists
    decrypted_api_key = None
    if server_settings.tileserver_api_key:
        decrypted_api_key = core_cryptography.decrypt_token_fernet(
            server_settings.tileserver_api_key
        )

    # Convert ORM model to schema and override the decrypted API key
    settings_schema = server_settings_schema.ServerSettingsRead.model_validate(
        server_settings
    )
    return settings_schema.model_copy(update={"tileserver_api_key": decrypted_api_key})


def get_tile_maps_templates() -> list[server_settings_schema.TileMapsTemplate]:
    """
    Retrieve a list of tile map templates.

    Returns:
        list[server_settings_schema.TileMapsTemplate]:
            A list of TileMapsTemplate objects for all tile maps.
    """
    templates = []
    for template_id, template_data in TILE_MAPS_TEMPLATES.items():
        templates.append(
            server_settings_schema.TileMapsTemplate(
                template_id=template_id, **template_data
            )
        )
    return templates


def extract_domain_from_tile_url(url: str) -> str | None:
    """
    Extract domain from tile server URL for CSP purposes.

    Args:
        url: Tile server URL template (e.g., https://tiles.example.com/map/{z}/{x}/{y}.png).

    Returns:
        Domain with protocol and wildcard (e.g., https://*.example.com) or None if invalid.

    Examples:
        - https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png -> https://*.openstreetmap.org
        - https://tiles.stadiamaps.com/tiles/{z}/{x}/{y}.png -> https://*.stadiamaps.com
    """
    try:
        # Replace common tile URL placeholders before parsing
        # {s} is used for subdomains (a, b, c for load balancing)
        clean_url = url.replace("{s}", "a").replace("{S}", "a")

        parsed = urlparse(clean_url)
        if not parsed.scheme or not parsed.netloc:
            return None

        # For localhost/IP addresses, return as-is
        if parsed.netloc.startswith("localhost") or parsed.netloc.startswith("127."):
            return f"{parsed.scheme}://{parsed.netloc}"

        # For regular domains, extract base domain for wildcard
        hostname = parsed.hostname or parsed.netloc

        # Split hostname and get the base domain (last 2 parts for most cases)
        # e.g., a.tile.openstreetmap.org -> openstreetmap.org
        # Then add wildcard: *.openstreetmap.org
        parts = hostname.split(".")
        if len(parts) >= 2:
            # Use last 2 parts as base domain (handles .com, .org, .co.uk, etc.)
            base_domain = ".".join(parts[-2:])
            return f"{parsed.scheme}://*.{base_domain}"

        # Fallback: use full hostname with wildcard
        return f"{parsed.scheme}://*.{hostname}"
    except Exception:
        return None


def get_allowed_tile_domains(db: Session) -> list[str]:
    """
    Get list of allowed tile domains for CSP img-src directive.

    This includes:
    - Built-in tile provider domains (from DEFAULT_ALLOWED_TILE_DOMAINS)
    - Custom tile server domain from server settings

    Args:
        db: Database session.

    Returns:
        List of domain patterns for CSP (e.g., ['https://*.tile.openstreetmap.org', 'https://*.stadiamaps.com']).
    """
    # Start with built-in providers
    allowed_domains: list[str] = (
        server_settings_schema.DEFAULT_ALLOWED_TILE_DOMAINS.copy()
    )

    # Add custom tile server domain if configured
    try:
        server_settings = get_server_settings(db)
        if server_settings and server_settings.tileserver_url:
            custom_domain = extract_domain_from_tile_url(server_settings.tileserver_url)
            if custom_domain and custom_domain not in allowed_domains:
                allowed_domains.append(custom_domain)
    except Exception:
        # If we can't get server settings, just use built-in providers
        core_logger.print_to_log(
            "Error retrieving server settings for allowed tile domains, using defaults",
            "debug",
        )
        pass

    return allowed_domains
