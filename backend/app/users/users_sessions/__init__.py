"""
User session management module.

This module provides session management including CRUD operations,
device detection, timeout validation, and token rotation for security.

Exports:
    - CRUD: get_user_sessions, get_session_by_id,
      get_session_by_id_not_expired, get_session_with_oauth_state,
      create_session, mark_tokens_exchanged, edit_session,
      delete_session, delete_idle_sessions, delete_sessions_by_family
    - Schemas: UsersSessionsBase, UsersSessionsRead,
      UsersSessionsInternal
    - Models: UsersSessions (ORM model)
    - Utils: DeviceType, DeviceInfo, validate_session_timeout,
      create_session_object, edit_session_object, create_session,
      edit_session, get_user_agent, get_ip_address,
      parse_user_agent, cleanup_idle_sessions
"""

from .crud import (
    get_user_sessions,
    get_session_by_id,
    get_session_by_id_not_expired,
    get_session_with_oauth_state,
    create_session,
    mark_tokens_exchanged,
    edit_session,
    delete_session,
    delete_idle_sessions,
    delete_sessions_by_family,
)
from .models import UsersSessions as UsersSessionsModel
from .schema import (
    UsersSessionsBase,
    UsersSessionsRead,
    UsersSessionsInternal,
)
from .utils import (
    DeviceType,
    DeviceInfo,
    validate_session_timeout,
    create_session_object,
    edit_session_object,
    get_user_agent,
    get_ip_address,
    parse_user_agent,
    cleanup_idle_sessions,
)

__all__ = [
    # CRUD operations
    "get_user_sessions",
    "get_session_by_id",
    "get_session_by_id_not_expired",
    "get_session_with_oauth_state",
    "create_session",
    "mark_tokens_exchanged",
    "edit_session",
    "delete_session",
    "delete_idle_sessions",
    "delete_sessions_by_family",
    # Database model
    "UsersSessionsModel",
    # Pydantic schemas
    "UsersSessionsBase",
    "UsersSessionsRead",
    "UsersSessionsInternal",
    # Utility classes and functions
    "DeviceType",
    "DeviceInfo",
    "validate_session_timeout",
    "create_session_object",
    "edit_session_object",
    "get_user_agent",
    "get_ip_address",
    "parse_user_agent",
    "cleanup_idle_sessions",
]
