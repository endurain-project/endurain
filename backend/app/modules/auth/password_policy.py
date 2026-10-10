"""Auth-owned password policy helpers.

Single source of truth for translating a user's access type
into the correct minimum password length and for delegating
validate+hash to IdentityService.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import modules.auth.identity_service as auth_identity_service
    import modules.server_settings.models as server_settings_models
    import modules.server_settings.schema as server_settings_schema


def resolve_password_min_length(
    server_settings: server_settings_models.ServerSettings | server_settings_schema.ServerSettingsRead,
    access_type: str,
) -> int:
    """
    Return minimum password length based on user access type.

    Args:
        server_settings: Settings containing password policy.
        access_type: User access type string ("admin" or other).

    Returns:
        Minimum password length as an integer.
    """
    if access_type == "admin":
        return server_settings.password_length_admin_users
    return server_settings.password_length_regular_users


def validate_and_hash_for_user(
    identity_service: auth_identity_service.IdentityService,
    server_settings: server_settings_models.ServerSettings | server_settings_schema.ServerSettingsRead,
    access_type: str,
    password: str,
) -> str:
    """
    Validate and hash a password using the user's policy.

    Args:
        identity_service: Identity service for hashing.
        server_settings: Settings containing password policy.
        access_type: User access type string ("admin" or other).
        password: Plaintext password to validate and hash.

    Returns:
        The hashed password string.

    Raises:
        HTTPException: If password fails validation.
    """
    min_length = resolve_password_min_length(server_settings, access_type)
    return identity_service.validate_and_hash_password(
        password,
        min_length,
        str(server_settings.password_type),
    )
