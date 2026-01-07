from fastapi import HTTPException, status
from sqlalchemy.orm import Session

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
