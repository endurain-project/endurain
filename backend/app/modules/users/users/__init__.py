"""
User module for user account management and authentication.

This module provides comprehensive user management including
account creation, profile updates, authentication, MFA support,
email verification, and admin approval workflows.

Exports:
    - CRUD: get_all_users, get_users_number,
      get_users_with_pagination, get_user_by_username,
      get_user_by_email, get_user_by_id, get_users_admin,
      create_user, create_signup_user, edit_user, approve_user,
      verify_user_email, update_user_photo,
      delete_user
    - Schemas: UsersBase, Users, UsersRead, UsersMe, UsersSignup,
      UsersCreate, UsersEditPassword, UsersListResponse
    - Enums: Gender, Language, WeekDay, UserAccessType
    - Utils: get_user_by_id_or_404, get_admin_users_or_404,
      check_user_is_active,
      create_user_default_data, save_user_image_file,
      delete_user_photo_filesystem
"""

from .crud import (
    approve_user,
    create_signup_user,
    create_user,
    delete_user,
    edit_user,
    get_all_users,
    get_user_by_email,
    get_user_by_id,
    get_user_by_username,
    get_users_admin,
    get_users_number,
    get_users_with_pagination,
    update_user_photo,
    verify_user_email,
)
from .schema import (
    Gender,
    Language,
    UserAccessType,
    Users,
    UsersBase,
    UsersCreate,
    UsersEditPassword,
    UsersListResponse,
    UsersMe,
    UsersRead,
    UsersSignup,
    WeekDay,
)
from .utils import (
    check_user_is_active,
    create_user_default_data,
    delete_user_photo_filesystem,
    get_admin_users_or_404,
    get_user_by_id_or_404,
    save_user_image_file,
)

__all__ = [
    "Gender",
    "Language",
    "UserAccessType",
    "Users",
    "UsersBase",
    "UsersCreate",
    "UsersEditPassword",
    "UsersListResponse",
    "UsersMe",
    "UsersRead",
    "UsersSignup",
    "WeekDay",
    "approve_user",
    "check_user_is_active",
    "create_signup_user",
    "create_user",
    "create_user_default_data",
    "delete_user",
    "delete_user_photo_filesystem",
    "edit_user",
    "get_admin_users_or_404",
    "get_all_users",
    "get_user_by_email",
    "get_user_by_id",
    "get_user_by_id_or_404",
    "get_user_by_username",
    "get_users_admin",
    "get_users_number",
    "get_users_with_pagination",
    "save_user_image_file",
    "update_user_photo",
    "verify_user_email",
]
