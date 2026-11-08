"""Credential policy and lifecycle operations."""

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.crud as credentials_crud
import modules.auth.credentials.password_breach as credentials_password_breach
import modules.auth.credentials.password_hasher as credentials_password_hasher
import modules.auth.credentials.password_policy as credentials_password_policy
import modules.server_settings.schema as server_settings_schema


def resolve_password_min_length(server_settings: server_settings_schema.ServerSettingsRead, access_type: str) -> int:
    """Return the configured minimum password length for the account type."""
    if access_type == "admin":
        return server_settings.password_length_admin_users
    return server_settings.password_length_regular_users


def allows_password_sign_in(server_settings: server_settings_schema.ServerSettingsRead, access_type: str) -> bool:
    """Return whether an account type may sign in with a local password under the server's settings.

    With local sign-in turned off, administrators keep it: they are the way back in when the identity provider
    is down, which is what the login page's ``forceLocalLogin`` escape is for.

    Args:
        server_settings: The server settings.
        access_type: The account's normalised access type.

    Returns:
        True when the account may sign in, or reset its password, with a local password.
    """
    return server_settings.local_login_enabled or access_type == "admin"


def get_credential(user_id: int, db: Session) -> credentials_contracts.CredentialRead | None:
    """Return a user's local credential, if present."""
    return credentials_crud.get_credential(user_id, db)


def is_password_change_required(user_id: int, db: Session) -> bool:
    """Return whether the user's password was set by an administrator and its owner must replace it."""
    credential = get_credential(user_id, db)
    return credential is not None and credential.password_change_required


def has_local_password(user_id: int, db: Session) -> bool:
    """Return whether the user has a local password."""
    return get_credential(user_id, db) is not None


def get_password_hash(user_id: int, db: Session) -> str | None:
    """Return the stored password hash for step-up verification."""
    credential = get_credential(user_id, db)
    return credential.password_hash if credential else None


def set_local_password_hash(user_id: int, password_hash: str, db: Session, *, change_required: bool) -> None:
    """Stage a user's local password hash.

    Every write of the hash says whether the owner must replace the password at the next sign-in: true when an
    administrator wrote it, false when the owner did, and unchanged for a rehash of the same password.

    Args:
        user_id: ID of the user whose credential is written.
        password_hash: The new password hash.
        db: SQLAlchemy session.
        change_required: Whether the owner must choose a new password at the next sign-in.
    """
    credentials_crud.upsert_password_hash(user_id, password_hash, change_required, db)


def require_password_change(user_id: int, db: Session) -> None:
    """Stage the requirement that a user choose a new password at their next password sign-in.

    Args:
        user_id: ID of the user who must replace their password.
        db: SQLAlchemy session.

    Raises:
        ConflictError: If the user has no local password, because there is nothing to replace.
    """
    if not has_local_password(user_id, db):
        raise core_exceptions.ConflictError("The user has no local password")
    credentials_crud.set_password_change_required(user_id, db)


def clear_local_password(user_id: int, db: Session) -> None:
    """Stage removal of a user's local password."""
    credentials_crud.delete_credential(user_id, db)


def hash_password(password: str) -> str:
    """Hash a password using the configured password hasher."""
    return credentials_password_hasher.get_password_hasher().hash_password(password)


def verify_and_update_password(
    password: str, stored_hash: str, password_hasher: credentials_password_hasher.PasswordHasher
) -> tuple[bool, str | None]:
    """Verify a typed local password against its stored hash, tolerating hashes made before NFC normalisation.

    The NFC form is tried first. A hash created from the raw text before passwords were normalised still verifies
    against the raw input and is then replaced by a hash of the NFC form.

    Args:
        password: The password as typed.
        stored_hash: The user's stored password hash.
        password_hasher: The hasher that verifies and rehashes.

    Returns:
        Whether the password is correct, and a replacement hash when the stored one should be updated.
    """
    normalised = credentials_password_policy.hash_form(password)
    verified, updated_hash = password_hasher.verify_and_update(normalised, stored_hash)
    if verified or normalised == password:
        return verified, updated_hash
    verified, _ = password_hasher.verify_and_update(password, stored_hash)
    if verified:
        return True, password_hasher.hash_password(normalised)
    return False, None


def dummy_verify_password(password: str, password_hasher: credentials_password_hasher.PasswordHasher) -> None:
    """Spend the Argon2 work of a failed :func:`verify_and_update_password` when there is no hash to verify against.

    A wrong password costs one verify of its NFC form, plus one of the raw input when that differs. Running the same
    number of dummy verifies keeps a missing or credential-less account indistinguishable by response time.

    Args:
        password: The password as typed.
        password_hasher: The hasher that runs the dummy verifies.
    """
    password_hasher.dummy_verify()
    if credentials_password_policy.hash_form(password) != password:
        password_hasher.dummy_verify()


def validate_and_hash_password_for_user(
    server_settings: server_settings_schema.ServerSettingsRead,
    access_type: str,
    password: str,
    *,
    username: str,
    email: str,
) -> str:
    """Validate a password under the account type's policy and return the hash of its NFC form.

    Args:
        server_settings: The server settings holding the minimum lengths.
        access_type: The account's normalised access type.
        password: The password as typed.
        username: The account's username.
        email: The account's email address.

    Returns:
        The password hash.

    Raises:
        PasswordBlankError: If the password is only whitespace.
        PasswordTooShortError: If the password is shorter than the account type's minimum.
        PasswordTooCommonError: If the password is on the blocklist.
        PasswordMatchesAccountError: If the password is or contains the username, the email or the application
            name.
    """
    min_length = resolve_password_min_length(server_settings, access_type)
    credentials_password_policy.check_password(password, min_length, username, email)
    return credentials_password_hasher.get_password_hasher().hash_password(
        credentials_password_policy.hash_form(password)
    )


def reject_breached_password(
    server_settings: server_settings_schema.ServerSettingsRead, password: str, db: Session
) -> None:
    """Refuse a password found in a known data breach when the administrator turned the check on.

    The check is a network call, so the open read transaction ends first: call this before the flow stages
    any write, as a rollback discards them.

    Args:
        server_settings: The server settings holding the breach-check switch.
        password: The password as typed.
        db: SQLAlchemy session whose open transaction ends before the call.

    Raises:
        PasswordBreachedError: If the check is on and the password appears in a known breach.
    """
    if not server_settings.password_breach_check_enabled:
        return
    db.rollback()
    if credentials_password_breach.is_breached(password):
        raise credentials_contracts.PasswordBreachedError()


def ensure_password_differs_from_current(user_id: int, new_password: str, db: Session) -> None:
    """Refuse a new password that is the account's current one, compared in the form passwords are stored in.

    Args:
        user_id: ID of the user whose password is being replaced.
        new_password: The new password as typed.
        db: SQLAlchemy session.

    Raises:
        PasswordUnchangedError: If the new password verifies against the stored hash.
    """
    stored_hash = get_password_hash(user_id, db)
    if stored_hash is None:
        return
    verified, _ = verify_and_update_password(
        new_password, stored_hash, credentials_password_hasher.get_password_hasher()
    )
    if verified:
        raise credentials_contracts.PasswordUnchangedError()
