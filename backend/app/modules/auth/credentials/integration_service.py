"""Credential operations used by authentication peers."""

from sqlalchemy.orm import Session

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.password_hasher as credentials_password_hasher
import modules.auth.credentials.service as credentials_service
import modules.server_settings.schema as server_settings_schema

PasswordHasher = credentials_password_hasher.PasswordHasher
PasswordPolicyError = credentials_password_hasher.PasswordPolicyError


def get_credential(user_id: int, db: Session) -> credentials_contracts.CredentialRead | None:
    """Return the user's local credential DTO."""
    return credentials_service.get_credential(user_id, db)


def get_password_hash(user_id: int, db: Session) -> str | None:
    """Return a user's stored local password hash."""
    return credentials_service.get_password_hash(user_id, db)


def has_local_password(user_id: int, db: Session) -> bool:
    """Return whether a user has a local password."""
    return credentials_service.has_local_password(user_id, db)


def set_local_password_hash(user_id: int, password_hash: str, db: Session) -> None:
    """Stage a user's local password hash."""
    credentials_service.set_local_password_hash(user_id, password_hash, db)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its stored hash."""
    return credentials_service.verify_password(password, password_hash)


def validate_and_hash_password_for_user(
    server_settings: server_settings_schema.ServerSettingsRead,
    access_type: str,
    password: str,
    db: Session,
) -> str:
    """Validate and hash a password using the account's configured policy."""
    return credentials_service.validate_and_hash_password_for_user(server_settings, access_type, password)


def get_password_hasher() -> credentials_password_hasher.PasswordHasher:
    """Return the configured password hasher."""
    return credentials_password_hasher.get_password_hasher()
