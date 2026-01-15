"""
Server settings module for configuration and database management.

This module provides server-wide configuration management, including
measurement units, currency settings, signup policies, SSO configuration,
and map tile server settings.

Exports:
    - CRUD operations: get_server_settings, edit_server_settings
    - Schemas: ServerSettings, ServerSettingsEdit, ServerSettingsRead,
      ServerSettingsReadPublic
    - Utilities: get_server_settings_or_404 (wrapper), get_tile_maps_templates
    - Models: ServerSettings (ORM model)
    - Enums: Units, Currency, PasswordType
"""

from .crud import get_server_settings as get_server_settings_db
from .crud import edit_server_settings
from .models import ServerSettings as ServerSettingsModel
from .schema import (
    ServerSettings,
    ServerSettingsBase,
    ServerSettingsEdit,
    ServerSettingsRead,
    ServerSettingsReadPublic,
    TileMapsTemplate,
    Units,
    Currency,
    PasswordType,
)
from .utils import get_server_settings_or_404, get_tile_maps_templates

__all__ = [
    # CRUD operations
    "get_server_settings_db",
    "edit_server_settings",
    # Database model
    "ServerSettingsModel",
    # Pydantic schemas
    "ServerSettings",
    "ServerSettingsBase",
    "ServerSettingsEdit",
    "ServerSettingsRead",
    "ServerSettingsReadPublic",
    "TileMapsTemplate",
    # Enums
    "Units",
    "Currency",
    "PasswordType",
    # Utility functions
    "get_server_settings_or_404",
    "get_tile_maps_templates",
]
