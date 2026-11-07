"""Credential operations used by authentication peers."""

from sqlalchemy.orm import Session

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.password_hasher as credentials_password_hasher
import modules.auth.credentials.service as credentials_service
import modules.server_settings.schema as server_settings_schema

PasswordHasher = credentials_password_hasher.PasswordHasher


def get_credential(user_id: int, db: Session) -> credentials_contracts.CredentialRead | None:
    """Return the user's local credential DTO."""
    return credentials_service.get_credential(user_id, db)


def is_password_change_required(user_id: int, db: Session) -> bool:
    """Return whether a user's password was set by an administrator and must be replaced at the next sign-in."""
    return credentials_service.is_password_change_required(user_id, db)


def get_password_hash(user_id: int, db: Session) -> str | None:
    """Return a user's stored local password hash."""
    return credentials_service.get_password_hash(user_id, db)


def has_local_password(user_id: int, db: Session) -> bool:
    """Return whether a user has a local password."""
    return credentials_service.has_local_password(user_id, db)


def set_local_password_hash(user_id: int, password_hash: str, db: Session, *, change_required: bool) -> None:
    """Stage a user's local password hash and whether its owner must replace the password at the next sign-in."""
    credentials_service.set_local_password_hash(user_id, password_hash, db, change_required=change_required)


def require_password_change(user_id: int, db: Session) -> None:
    """Stage the requirement that a user replace their password at the next sign-in, keeping the current one."""
    credentials_service.require_password_change(user_id, db)


def validate_and_hash_password_for_user(
    server_settings: server_settings_schema.ServerSettingsRead,
    access_type: str,
    password: str,
    db: Session,
    *,
    username: str,
    email: str,
) -> str:
    """Validate a password against the account's policy, username and email, and return its hash."""
    return credentials_service.validate_and_hash_password_for_user(
        server_settings, access_type, password, username=username, email=email
    )


def ensure_password_differs_from_current(user_id: int, new_password: str, db: Session) -> None:
    """Refuse a new password that is the user's current one."""
    credentials_service.ensure_password_differs_from_current(user_id, new_password, db)


def verify_and_update_password(
    password: str, stored_hash: str, password_hasher: credentials_password_hasher.PasswordHasher
) -> tuple[bool, str | None]:
    """Verify a typed password against its stored hash; a replacement hash is returned when it should be updated."""
    return credentials_service.verify_and_update_password(password, stored_hash, password_hasher)


def allows_password_sign_in(server_settings: server_settings_schema.ServerSettingsRead, access_type: str) -> bool:
    """Return whether an account type may sign in with a local password under the server's settings."""
    return credentials_service.allows_password_sign_in(server_settings, access_type)


def get_password_hasher() -> credentials_password_hasher.PasswordHasher:
    """Return the configured password hasher."""
    return credentials_password_hasher.get_password_hasher()
