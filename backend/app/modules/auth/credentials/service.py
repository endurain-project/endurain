"""Credential policy and lifecycle operations."""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.credentials.crud as credentials_crud
import modules.auth.credentials.password_hasher as credentials_password_hasher
import modules.server_settings.schema as server_settings_schema


def resolve_password_min_length(server_settings: server_settings_schema.ServerSettingsRead, access_type: str) -> int:
    """Return the configured minimum password length for the account type."""
    if access_type == "admin":
        return server_settings.password_length_admin_users
    return server_settings.password_length_regular_users


def get_credential(user_id: int, db: Session):
    """Return a user's local credential, if present."""
    return credentials_crud.get_credential(user_id, db)


def has_local_password(user_id: int, db: Session) -> bool:
    """Return whether the user has a local password."""
    return get_credential(user_id, db) is not None


def get_password_hash(user_id: int, db: Session) -> str | None:
    """Return the stored password hash for step-up verification."""
    credential = get_credential(user_id, db)
    return credential.password_hash if credential else None


def set_local_password_hash(user_id: int, password_hash: str, db: Session) -> None:
    """Stage a user's local password hash."""
    credentials_crud.upsert_password_hash(user_id, password_hash, db)


def clear_local_password(user_id: int, db: Session) -> None:
    """Stage removal of a user's local password."""
    credentials_crud.delete_credential(user_id, db)


def hash_password(password: str) -> str:
    """Hash a password using the configured password hasher."""
    return credentials_password_hasher.get_password_hasher().hash_password(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored hash."""
    return credentials_password_hasher.get_password_hasher().verify_password(password, password_hash)


def validate_and_hash_password(password: str, min_length: int, password_type: str) -> str:
    """Validate a password under the given policy and return its hash."""
    password_hasher = credentials_password_hasher.get_password_hasher()
    try:
        password_hasher.validate_password(password, min_length, password_type)
    except credentials_password_hasher.PasswordPolicyError as err:
        raise core_exceptions.InvalidInputError(str(err)) from err
    return password_hasher.hash_password(password)


def validate_and_hash_password_for_user(
    server_settings: server_settings_schema.ServerSettingsRead,
    access_type: str,
    password: str,
) -> str:
    """Validate and hash a password using the user's configured policy."""
    min_length = resolve_password_min_length(server_settings, access_type)
    return validate_and_hash_password(password, min_length, str(server_settings.password_type))
