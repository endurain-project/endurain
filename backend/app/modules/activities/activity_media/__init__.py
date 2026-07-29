"""
Activity media sub-module for photos attached to an activity.

This module provides persistence, application logic, schemas, ORM models, and
routes for media files (currently photos) associated with a user's activities,
including upload, retrieval, and deletion.

Exports:
    - CRUD: get_all_activity_media, get_activity_media_by_id,
      get_media_for_activity, get_activities_media, create_activity_media,
      create_activity_medias, edit_activity_media_media_path,
      delete_activity_media
    - Service: list_activity_media, store_activity_media,
      delete_activity_media (permission-checked, storage-aware)
    - Contracts: ActivityMediaRecord (persisted record, carries the storage key)
    - Schemas: ActivityMedia (API read model, carries the servable URL)
    - Models: ActivityMedia (ORM model)
    - Routers: router, public_router
"""

from .crud import (
    create_activity_media,
    create_activity_medias,
    delete_activity_media,
    edit_activity_media_media_path,
    get_activities_media,
    get_activity_media_by_id,
    get_all_activity_media,
    get_media_for_activity,
)
from .models import ActivityMedia as ActivityMediaModel
from .schema import ActivityMedia
from .service import list_activity_media, store_activity_media

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
    "get_activity_media_by_id",
    # CRUD operations
    "get_all_activity_media",
    "get_media_for_activity",
    # Application logic
    "list_activity_media",
    "store_activity_media",
]
