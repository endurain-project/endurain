"""
Activity media sub-module for photos attached to an activity.

This module provides CRUD operations, schemas, ORM models, and routes
for media files (currently photos) associated with a user's activities,
including upload, retrieval, and deletion.

Exports:
    - CRUD: get_all_activity_media, get_activity_media,
      get_activities_media, create_activity_media,
      create_activity_medias, edit_activity_media_media_path,
      delete_activity_media
    - Schemas: ActivityMedia
    - Models: ActivityMedia (ORM model)
    - Routers: router
"""

from .crud import (
    create_activity_media,
    create_activity_medias,
    delete_activity_media,
    edit_activity_media_media_path,
    get_activities_media,
    get_activity_media,
    get_all_activity_media,
)
from .models import ActivityMedia as ActivityMediaModel
from .schema import ActivityMedia

__all__ = [
    # Pydantic schemas
    "ActivityMedia",
    # Database model
    "ActivityMediaModel",
    "create_activity_media",
    "create_activity_medias",
    "delete_activity_media",
    "edit_activity_media_media_path",
    "get_activities_media",
    "get_activity_media",
    # CRUD operations
    "get_all_activity_media",
]
