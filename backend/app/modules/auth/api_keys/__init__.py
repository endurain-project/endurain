"""
API key management module.

This module provides API key lifecycle management including
creation, validation, revocation, and deletion.
"""

from .crud import (
    create_api_key,
    delete_api_key,
    get_api_key_by_hash,
    get_api_key_by_id,
    get_api_keys_by_user_id,
    revoke_api_key,
    update_last_used,
)
from .models import UsersApiKeys as UsersApiKeysModel
from .schema import (
    UsersApiKeyCreate,
    UsersApiKeyCreated,
    UsersApiKeyRead,
)
from .utils import (
    generate_api_key,
    hash_api_key,
    validate_api_key_scopes,
)

__all__ = [
    "UsersApiKeyCreate",
    "UsersApiKeyCreated",
    "UsersApiKeyRead",
    "UsersApiKeysModel",
    "create_api_key",
    "delete_api_key",
    "generate_api_key",
    "get_api_key_by_hash",
    "get_api_key_by_id",
    "get_api_keys_by_user_id",
    "hash_api_key",
    "revoke_api_key",
    "update_last_used",
    "validate_api_key_scopes",
]
