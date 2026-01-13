"""
User integrations module for third-party service OAuth management.

This module provides CRUD operations and data models for user
integration settings including Strava and Garmin Connect OAuth
tokens and synchronization preferences.

Exports:
    - CRUD: get_user_integrations_by_user_id, create_user_integrations,
      edit_user_integrations, link_strava_account, unlink_strava_account,
      set_user_strava_client, set_user_strava_state, set_user_strava_sync_gear,
      link_garminconnect_account, unlink_garminconnect_account,
      set_user_garminconnect_sync_gear, get_user_integrations_by_strava_state
    - Schemas: UsersIntegrationsBase, UsersIntegrationsCreate,
      UsersIntegrationsRead, UsersIntegrationsUpdate
    - Models: UsersIntegrations (ORM model)
"""

from .crud import (
    get_user_integrations_by_user_id,
    get_user_integrations_by_strava_state,
    create_user_integrations,
    edit_user_integrations,
    link_strava_account,
    unlink_strava_account,
    set_user_strava_client,
    set_user_strava_state,
    set_user_strava_sync_gear,
    link_garminconnect_account,
    unlink_garminconnect_account,
    set_user_garminconnect_sync_gear,
)
from .models import UsersIntegrations as UsersIntegrationsModel
from .schema import (
    UsersIntegrationsBase,
    UsersIntegrationsCreate,
    UsersIntegrationsRead,
    UsersIntegrationsUpdate,
)

__all__ = [
    # CRUD operations
    "get_user_integrations_by_user_id",
    "get_user_integrations_by_strava_state",
    "create_user_integrations",
    "edit_user_integrations",
    "link_strava_account",
    "unlink_strava_account",
    "set_user_strava_client",
    "set_user_strava_state",
    "set_user_strava_sync_gear",
    "link_garminconnect_account",
    "unlink_garminconnect_account",
    "set_user_garminconnect_sync_gear",
    # Database model
    "UsersIntegrationsModel",
    # Pydantic schemas
    "UsersIntegrationsBase",
    "UsersIntegrationsCreate",
    "UsersIntegrationsRead",
    "UsersIntegrationsUpdate",
]
