"""Temporary MFA setup secret storage with TTL, backed by the platform state.

The plaintext TOTP secret is Fernet-encrypted in this module and only the
ciphertext is handed to the ``StateProvider`` (an in-process dict under
``local``, Redis under ``distributed``); this module no longer knows which
backend is used.
"""

from typing import NoReturn

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_MFA_SECRET_KEY_PREFIX = "endurain:auth:mfa:setup_secret"  # noqa: S105 - storage key prefix, not a credential
_DEFAULT_TTL_SECONDS: int = 300


class MFASecretStoreUnavailableError(core_exceptions.ServiceUnavailableError, RuntimeError):
    """Raised when MFA secret storage cannot be reached.

    Answered as a 503 by the API boundary, so a route needs no handler of its own.

    Attributes:
        None.
    """

    default_detail = "MFA setup temporarily unavailable"


def _raise_store_unavailable(err: StateBackendUnavailableError) -> NoReturn:
    """Log a storage outage and re-raise it as an MFA-store error.

    Args:
        err: The provider outage error.

    Raises:
        MFASecretStoreUnavailableError: Always raised.
    """
    raise MFASecretStoreUnavailableError("MFA secret storage is unavailable") from err


def _user_id_digest(user_id: int) -> str:
    """Hash a user ID for storage key names.

    Args:
        user_id: User ID to hash.

    Returns:
        SHA-256 digest for use in the storage key.

    Raises:
        None.
    """
    return core_hashing.sha256_hex(str(user_id))


def _encrypt_secret(secret: str) -> str:
    """Encrypt a plaintext MFA secret.

    Args:
        secret: Plaintext MFA setup secret.

    Returns:
        Fernet-encrypted secret.

    Raises:
        ValueError: When encryption returns no value.
        ProcessingError: When Fernet encryption fails.
    """
    encrypted_secret = core_cryptography.encrypt_token_fernet(secret)
    if not encrypted_secret:
        raise ValueError("Failed to encrypt MFA secret")
    return encrypted_secret


def _decrypt_secret(encrypted_secret: str) -> str | None:
    """Decrypt an encrypted MFA secret.

    Args:
        encrypted_secret: Fernet-encrypted MFA setup secret.

    Returns:
        Decrypted MFA setup secret, or None when it cannot be decrypted.

    Raises:
        None.
    """
    try:
        return core_cryptography.decrypt_token_fernet(encrypted_secret)
    except core_exceptions.CryptographyError as err:
        logger.warning("Could not decrypt the stored MFA setup secret", exc_info=err)
        return None


class MFASecretStore:
    """Temporary encrypted MFA setup-secret storage backed by the platform state.

    Attributes:
        DEFAULT_TTL_SECONDS: Default secret lifetime in seconds.
        _state: Explicit platform state provider.
    """

    DEFAULT_TTL_SECONDS: int = _DEFAULT_TTL_SECONDS

    def __init__(self, state: StateProvider) -> None:
        """Initialize the MFA secret store.

        Args:
            state: Platform state provider.
        """
        self._state = state

    def _key(self, user_id: int) -> str:
        """Build the storage key for a user's pending MFA secret."""
        return f"{_MFA_SECRET_KEY_PREFIX}:{_user_id_digest(user_id)}"

    def add_secret(self, user_id: int, secret: str) -> None:
        """Encrypt and store an MFA setup secret with TTL.

        Args:
            user_id: User ID to associate with the secret.
            secret: Plaintext MFA secret to encrypt and store.

        Raises:
            MFASecretStoreUnavailableError: When storage is unavailable.
            ValueError: If encryption fails.
            ProcessingError: If Fernet encryption fails.
        """
        encrypted_secret = _encrypt_secret(secret)
        try:
            self._state.set(self._key(user_id), encrypted_secret.encode(), ttl_seconds=_DEFAULT_TTL_SECONDS)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)

    def get_secret(self, user_id: int) -> str | None:
        """Retrieve and decrypt an MFA secret if present.

        Args:
            user_id: User ID to retrieve the secret for.

        Returns:
            Decrypted MFA secret, or None when missing or invalid.

        Raises:
            MFASecretStoreUnavailableError: When storage is unavailable.
        """
        try:
            encrypted_secret = self._state.get(self._key(user_id))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        if encrypted_secret is None:
            return None
        return _decrypt_secret(encrypted_secret.decode())

    def delete_secret(self, user_id: int) -> None:
        """Remove an MFA secret from storage.

        Failures are swallowed because the entry expires via TTL anyway.

        Args:
            user_id: User ID whose secret should be removed.

        Returns:
            None.
        """
        try:
            self._state.delete(self._key(user_id))
        except StateBackendUnavailableError:
            return

    def has_secret(self, user_id: int) -> bool:
        """Check if a non-expired secret exists for a user.

        Args:
            user_id: User ID to check.

        Returns:
            True if a secret exists, False otherwise.

        Raises:
            MFASecretStoreUnavailableError: When storage is unavailable.
        """
        try:
            return self._state.get(self._key(user_id)) is not None
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)

    def clear_all(self) -> None:
        """Remove all MFA setup secrets from storage.

        Returns:
            None.

        Raises:
            MFASecretStoreUnavailableError: When storage is unavailable.
        """
        try:
            self._state.delete_prefix(f"{_MFA_SECRET_KEY_PREFIX}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
