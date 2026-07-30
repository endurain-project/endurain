"""Temporary MFA setup secret storage with TTL, backed by the platform state.

The plaintext TOTP secret is Fernet-encrypted in this module and only the
ciphertext is handed to the ``StateProvider`` (an in-process dict under
``local``, Redis under ``distributed``); this module no longer knows which
backend is used.
"""

from typing import NoReturn

import core.cryptography as core_cryptography
import core.hashing as core_hashing
import core.logger as core_logger
import infra.runtime as platform_runtime
from infra.providers import StateBackendUnavailableError, StateProvider

_MFA_SECRET_KEY_PREFIX = "endurain:auth:mfa:setup_secret"  # noqa: S105 - storage key prefix, not a credential
_DEFAULT_TTL_SECONDS: int = 300


class MFASecretStoreUnavailableError(RuntimeError):
    """
    Raised when MFA secret storage cannot be reached.

    Attributes:
        None.
    """


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """
    Log a storage outage and re-raise it as an MFA-store error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        MFASecretStoreUnavailableError: Always raised.
    """
    core_logger.print_to_log(f"MFA secret storage failed: {operation}", "error", exc=err)
    raise MFASecretStoreUnavailableError("MFA secret storage is unavailable") from err


def _user_id_digest(user_id: int) -> str:
    """
    Hash a user ID for storage key names.

    Args:
        user_id: User ID to hash.

    Returns:
        SHA-256 digest for use in the storage key.

    Raises:
        None.
    """
    return core_hashing.sha256_hex(str(user_id))


def _encrypt_secret(secret: str) -> str:
    """
    Encrypt a plaintext MFA secret.

    Args:
        secret: Plaintext MFA setup secret.

    Returns:
        Fernet-encrypted secret.

    Raises:
        ValueError: When encryption returns no value.
        HTTPException: When Fernet encryption fails.
    """
    encrypted_secret = core_cryptography.encrypt_token_fernet(secret)
    if not encrypted_secret:
        raise ValueError("Failed to encrypt MFA secret")
    return encrypted_secret


def _decrypt_secret(encrypted_secret: str, user_id: int) -> str | None:
    """
    Decrypt an encrypted MFA secret.

    Args:
        encrypted_secret: Fernet-encrypted MFA setup secret.
        user_id: User ID used for sanitized logging.

    Returns:
        Decrypted MFA setup secret, or None on failure.

    Raises:
        None.
    """
    try:
        return core_cryptography.decrypt_token_fernet(encrypted_secret)
    except Exception as err:
        core_logger.print_to_log(
            f"Failed to decrypt MFA secret for user {user_id}: {type(err).__name__}",
            "error",
            exc=err,
        )
        return None


def _log_secret_stored(user_id: int, ttl_seconds: int) -> None:
    """
    Log MFA secret storage without exposing the secret.

    Args:
        user_id: User ID associated with the setup secret.
        ttl_seconds: Secret time-to-live in seconds.

    Returns:
        None.

    Raises:
        None.
    """
    core_logger.print_to_log(
        f"Securely stored MFA secret for user {user_id} (expires in {ttl_seconds}s)",
        "debug",
    )


class MFASecretStore:
    """
    Temporary encrypted MFA setup-secret storage backed by the platform state.

    Attributes:
        DEFAULT_TTL_SECONDS: Default secret lifetime in seconds.
        _state_override: Explicit provider (tests); ``None`` resolves the
            process-wide provider lazily at call time.
        _ttl_seconds: Secret lifetime in seconds.
    """

    DEFAULT_TTL_SECONDS: int = _DEFAULT_TTL_SECONDS

    def __init__(self, state: StateProvider | None = None, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        """
        Initialize the MFA secret store.

        Args:
            state: Optional explicit state provider (defaults to the process-wide one).
            ttl_seconds: Time-to-live for secrets in seconds.
        """
        self._state_override = state
        self._ttl_seconds = ttl_seconds

    @property
    def _state(self) -> StateProvider:
        return self._state_override if self._state_override is not None else platform_runtime.get_state()

    def _key(self, user_id: int) -> str:
        """Build the storage key for a user's pending MFA secret."""
        return f"{_MFA_SECRET_KEY_PREFIX}:{_user_id_digest(user_id)}"

    def add_secret(self, user_id: int, secret: str) -> None:
        """
        Encrypt and store an MFA setup secret with TTL.

        Args:
            user_id: User ID to associate with the secret.
            secret: Plaintext MFA secret to encrypt and store.

        Raises:
            MFASecretStoreUnavailableError: When storage is unavailable.
            ValueError: If encryption fails.
            HTTPException: If Fernet encryption fails.
        """
        encrypted_secret = _encrypt_secret(secret)
        try:
            self._state.set(self._key(user_id), encrypted_secret.encode(), ttl_seconds=self._ttl_seconds)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("add MFA setup secret", err)
        _log_secret_stored(user_id, self._ttl_seconds)

    def get_secret(self, user_id: int) -> str | None:
        """
        Retrieve and decrypt an MFA secret if present.

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
            _raise_store_unavailable("get MFA setup secret", err)
        if encrypted_secret is None:
            return None
        return _decrypt_secret(encrypted_secret.decode(), user_id)

    def delete_secret(self, user_id: int) -> None:
        """
        Remove an MFA secret from storage.

        Failures are swallowed because the entry expires via TTL anyway.

        Args:
            user_id: User ID whose secret should be removed.

        Returns:
            None.
        """
        try:
            self._state.delete(self._key(user_id))
        except StateBackendUnavailableError as err:
            core_logger.print_to_log(
                "Failed to delete MFA setup secret; entry will expire naturally via TTL",
                "warning",
                exc=err,
            )

    def has_secret(self, user_id: int) -> bool:
        """
        Check if a non-expired secret exists for a user.

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
            _raise_store_unavailable("check MFA setup secret", err)

    def clear_all(self) -> None:
        """
        Remove all MFA setup secrets from storage.

        Returns:
            None.

        Raises:
            MFASecretStoreUnavailableError: When storage is unavailable.
        """
        try:
            self._state.delete_prefix(f"{_MFA_SECRET_KEY_PREFIX}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("clear MFA setup secrets", err)


# Single provider-backed implementation; the alias is kept for existing call
# sites that annotate against the store type.
MFASecretStoreBackend = MFASecretStore

mfa_secret_store = MFASecretStore()


def get_mfa_secret_store() -> MFASecretStore:
    """
    Get the module-level MFA secret store instance.

    Returns:
        The global MFA secret store instance.

    Raises:
        None.
    """
    return mfa_secret_store
