"""
User privacy settings module for activity visibility control.

This module provides CRUD operations and data models for user
privacy settings including activity visibility levels and various
data hiding options for activities.

Exports:
    - CRUD: get_user_privacy_settings_by_user_id,
      create_user_privacy_settings, edit_user_privacy_settings
    - Schemas: UsersPrivacySettingsBase, UsersPrivacySettingsCreate,
      UsersPrivacySettingsRead, UsersPrivacySettingsUpdate
    - Models: UsersPrivacySettings (ORM model)
    - Enums: ActivityVisibility
"""

from .crud import (
    create_user_privacy_settings,
    edit_user_privacy_settings,
    get_user_privacy_settings_by_user_id,
)
from .schema import (
    ActivityVisibility,
    UsersPrivacySettingsBase,
    UsersPrivacySettingsCreate,
    UsersPrivacySettingsRead,
    UsersPrivacySettingsUpdate,
)

__all__ = [
    "ActivityVisibility",
    "UsersPrivacySettingsBase",
    "UsersPrivacySettingsCreate",
    "UsersPrivacySettingsRead",
    "UsersPrivacySettingsUpdate",
    "create_user_privacy_settings",
    "edit_user_privacy_settings",
    "get_user_privacy_settings_by_user_id",
]
