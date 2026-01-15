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
      verify_user_email, edit_user_password, update_user_photo,
      update_user_mfa, delete_user
    - Schemas: UserBase, User, UserRead, UserMe, UserSignup,
      UserCreate, UserEditPassword, UserListResponse
    - Models: User (ORM model)
    - Enums: Gender, Language, WeekDay, UserAccessType
    - Utils: get_user_by_id_or_404, get_admin_users_or_404,
      check_password_and_hash, check_user_is_active,
      create_user_default_data, save_user_image_file,
      delete_user_photo_filesystem
"""

from .crud import (
    get_all_users,
    get_users_number,
    get_users_with_pagination,
    get_user_by_username,
    get_user_by_email,
    get_user_by_id,
    get_users_admin,
    create_user,
    create_signup_user,
    edit_user,
    approve_user,
    verify_user_email,
    edit_user_password,
    update_user_photo,
    update_user_mfa,
    delete_user,
)
from .models import User as UserModel
from .schema import (
    Gender,
    Language,
    WeekDay,
    UserAccessType,
    UserBase,
    User,
    UserRead,
    UserMe,
    UserSignup,
    UserCreate,
    UserEditPassword,
    UserListResponse,
)
from .utils import (
    get_user_by_id_or_404,
    get_admin_users_or_404,
    check_password_and_hash,
    check_user_is_active,
    create_user_default_data,
    save_user_image_file,
    delete_user_photo_filesystem,
)

__all__ = [
    # CRUD operations
    "get_all_users",
    "get_users_number",
    "get_users_with_pagination",
    "get_user_by_username",
    "get_user_by_email",
    "get_user_by_id",
    "get_users_admin",
    "create_user",
    "create_signup_user",
    "edit_user",
    "approve_user",
    "verify_user_email",
    "edit_user_password",
    "update_user_photo",
    "update_user_mfa",
    "delete_user",
    # Database model
    "UserModel",
    # Pydantic schemas
    "UserBase",
    "User",
    "UserRead",
    "UserMe",
    "UserSignup",
    "UserCreate",
    "UserEditPassword",
    "UserListResponse",
    # Enums
    "Gender",
    "Language",
    "WeekDay",
    "UserAccessType",
    # Utility functions
    "get_user_by_id_or_404",
    "get_admin_users_or_404",
    "check_password_and_hash",
    "check_user_is_active",
    "create_user_default_data",
    "save_user_image_file",
    "delete_user_photo_filesystem",
]
