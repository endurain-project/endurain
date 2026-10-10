"""
Auth identity links module for SSO/OAuth account linking.

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
    - Models: IdentityLink (ORM model)
    - Utils:
      get_user_identity_provider_refresh_token_by_user_id_and_idp_id,
      enrich_user_identity_providers
"""

from .crud import (
    check_user_identity_providers_by_idp_id,
    clear_user_identity_provider_refresh_token_by_user_id_and_idp_id,
    create_user_identity_provider,
    delete_user_identity_provider,
    get_user_identity_provider_by_subject_and_idp_id,
    get_user_identity_provider_by_user_id_and_idp_id,
    get_user_identity_providers_by_user_id,
    store_user_identity_provider_tokens,
    update_user_identity_provider_last_login,
)
from .models import IdentityLink
from .schema import (
    UsersIdentityProviderBase,
    UsersIdentityProviderCreate,
    UsersIdentityProviderRead,
    UsersIdentityProviderResponse,
    UsersIdentityProviderTokenUpdate,
)
from .utils import (
    enrich_user_identity_providers,
    get_user_identity_provider_refresh_token_by_user_id_and_idp_id,
)

__all__ = [
    # Database model
    "IdentityLink",
    # Pydantic schemas
    "UsersIdentityProviderBase",
    "UsersIdentityProviderCreate",
    "UsersIdentityProviderRead",
    "UsersIdentityProviderResponse",
    "UsersIdentityProviderTokenUpdate",
    # CRUD operations
    "check_user_identity_providers_by_idp_id",
    "clear_user_identity_provider_refresh_token_by_user_id_and_idp_id",
    "create_user_identity_provider",
    "delete_user_identity_provider",
    "enrich_user_identity_providers",
    "get_user_identity_provider_by_subject_and_idp_id",
    "get_user_identity_provider_by_user_id_and_idp_id",
    # Utility functions
    "get_user_identity_provider_refresh_token_by_user_id_and_idp_id",
    "get_user_identity_providers_by_user_id",
    "store_user_identity_provider_tokens",
    "update_user_identity_provider_last_login",
]
