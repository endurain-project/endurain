"""Change detection and secret handling shared by the server-settings services.

Pure: no session, no configuration and no I/O.
"""

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions


def decrypt_secret(token: str | None, label: str) -> str | None:
    """Decrypt a stored secret.

    Args:
        token: The stored (encrypted) secret, or None / empty when unset.
        label: What the secret is, for the error message (for example "SMTP password").

    Returns:
        The plain-text secret, or None when none is set.

    Raises:
        ServiceUnavailableError: When the stored secret cannot be decrypted, for example
            after the encryption key changed.
    """
    if not token:
        return None
    try:
        return core_cryptography.decrypt_token_fernet(token)
    except core_exceptions.CryptographyError as err:
        raise core_exceptions.ServiceUnavailableError(
            f"The stored {label} cannot be decrypted; enter it again in the server settings"
        ) from err


def secret_changed(stored_token: str | None, new_plain: str | None, label: str) -> bool:
    """Return whether a submitted secret differs from the stored one.

    The comparison is in plain text, since the stored token is encrypted and a fresh
    encryption of the same secret never matches it. A stored secret that can no longer
    be decrypted counts as changed, so it can always be replaced or removed.

    Args:
        stored_token: The stored (encrypted) secret.
        new_plain: The submitted plain-text secret.
        label: What the secret is, for the decryption error message.

    Returns:
        True when the submitted secret is not the stored one.
    """
    try:
        stored = decrypt_secret(stored_token, label)
    except core_exceptions.ServiceUnavailableError:
        return True
    return (stored or None) != (new_plain or None)


def encrypt_secret(plain: str | None) -> str | None:
    """Encrypt a secret for storage.

    Args:
        plain: The plain-text secret.

    Returns:
        The encrypted token, or None when the secret is empty.
    """
    return core_cryptography.encrypt_token_fernet(plain) if plain else None


def changed_fields(
    attributes: BaseModel,
    current: BaseModel,
    secret_fields: dict[str, str],
) -> set[str]:
    """Return the sent fields whose value differs from the stored one.

    The secrets are compared in plain text, since the stored token is encrypted
    and a fresh encryption of the same secret never matches it. A stored secret that
    can no longer be decrypted counts as changed, so it can always be replaced or removed.

    Args:
        attributes: The request body.
        current: The settings as stored.
        secret_fields: Write-only secret field name to what it is called in messages.

    Returns:
        The names of the fields the request actually changes.
    """
    changed: set[str] = set()
    for field, value in attributes.model_dump(exclude_unset=True).items():
        if field in secret_fields:
            if secret_changed(getattr(current, field), value, secret_fields[field]):
                changed.add(field)
        elif getattr(current, field) != value:
            changed.add(field)
    return changed


def differing(current: BaseModel, target: dict[str, Any]) -> dict[str, Any]:
    """Return the target fields whose value differs from the stored one.

    Args:
        current: The settings as stored.
        target: Field name to the value it should have.

    Returns:
        The fields to write.
    """
    return {field: value for field, value in target.items() if getattr(current, field) != value}


def refuse_env_managed(
    changed_fields: set[str], env_managed: dict[str, str], order: Iterable[str] | None = None
) -> None:
    """Refuse a change to a field an environment variable sets.

    Args:
        changed_fields: The fields the request changes.
        env_managed: Field name to the environment variable that sets it.
        order: The order to name the fields in; sorted when omitted.

    Raises:
        ConflictError: If a changed field is set by an environment variable.
    """
    managed_changes = [
        field for field in (order or sorted(env_managed)) if field in changed_fields & env_managed.keys()
    ]
    if managed_changes:
        raise core_exceptions.ConflictError(
            "; ".join(
                f"{field} is set by the {env_managed[field]} environment variable; remove it to edit this setting here"
                for field in managed_changes
            )
        )
