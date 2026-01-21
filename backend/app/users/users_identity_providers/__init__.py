"""
User identity provider module for SSO/OAuth account linking.

This module provides CRUD operations and data models for managing
user-to-identity-provider associations, including token storage
and last login tracking.

Exports:
    - CRUD: check_user_identity_providers_by_idp_id,
      get_user_identity_providers_by_user_id,
      get_user_identity_provider_by_user_id_and_idp_id,
      get_user_identity_provider_by_subject_and_idp_id,
      create_user_identity_provider,
      update_user_identity_provider_last_login,
      store_user_identity_provider_tokens,
      clear_user_identity_provider_refresh_token_by_user_id_and_idp_id,
      delete_user_identity_provider
    - Schemas: UsersIdentityProviderBase, UsersIdentityProviderCreate,
      UsersIdentityProviderRead, UsersIdentityProviderResponse,
      UsersIdentityProviderTokenUpdate
    - Models: UsersIdentityProvider (ORM model)
    - Utils: get_user_identity_provider_refresh_token_by_user_id_and_idp_id
"""

from .crud import (
    check_user_identity_providers_by_idp_id,
    get_user_identity_providers_by_user_id,
    get_user_identity_provider_by_user_id_and_idp_id,
    get_user_identity_provider_by_subject_and_idp_id,
    create_user_identity_provider,
    update_user_identity_provider_last_login,
    store_user_identity_provider_tokens,
    clear_user_identity_provider_refresh_token_by_user_id_and_idp_id,
    delete_user_identity_provider,
)
from .models import UsersIdentityProvider as UserIdentityProviderModel
from .schema import (
    UsersIdentityProviderBase,
    UsersIdentityProviderCreate,
    UsersIdentityProviderRead,
    UsersIdentityProviderResponse,
    UsersIdentityProviderTokenUpdate,
)
from .utils import (
    get_user_identity_provider_refresh_token_by_user_id_and_idp_id,
)

__all__ = [
    # CRUD operations
    "check_user_identity_providers_by_idp_id",
    "get_user_identity_providers_by_user_id",
    "get_user_identity_provider_by_user_id_and_idp_id",
    "get_user_identity_provider_by_subject_and_idp_id",
    "create_user_identity_provider",
    "update_user_identity_provider_last_login",
    "store_user_identity_provider_tokens",
    "clear_user_identity_provider_refresh_token_by_user_id_and_idp_id",
    "delete_user_identity_provider",
    # Database model
    "UserIdentityProviderModel",
    # Pydantic schemas
    "UsersIdentityProviderBase",
    "UsersIdentityProviderCreate",
    "UsersIdentityProviderRead",
    "UsersIdentityProviderResponse",
    "UsersIdentityProviderTokenUpdate",
    # Utility functions
    "get_user_identity_provider_refresh_token_by_user_id_and_idp_id",
]
