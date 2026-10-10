"""Temporary Garmin MFA code storage for cross-request handoff.

The Garmin Connect link flow is asynchronous: the backend starts a blocking
login in a thread that eventually calls back for an MFA code, while the user
submits that code via a separate HTTP request.  In a multi-worker deployment
these two requests may land on different processes, so the code is kept in the
platform ``StateProvider`` (an in-process dict under ``local``, Redis under
``distributed``) — this module no longer knows or cares which backend is used.

Interface::

    add_code(user_id, code)   - store the MFA code for user_id
    get_code(user_id)         - retrieve it (does NOT delete)
    delete_code(user_id)      - remove it after consumption
    has_code(user_id)         - check whether a live code exists
    clear_all()               - remove all codes (for tests / admin)
"""

from typing import NoReturn

import jasil.runtime as platform_runtime
from jasil.providers import StateBackendUnavailableError, StateProvider

import core.hashing as core_hashing
import core.logger as core_logger

logger = core_logger.get_logger(__name__)

_GARMIN_MFA_KEY_PREFIX = "endurain:garmin:mfa:code"
# TTL must exceed the 65-second blocking_login timeout in garmin/utils.py.
_DEFAULT_TTL_SECONDS: int = 90


class GarminMFACodeStoreUnavailableError(RuntimeError):
    """
    Raised when the Garmin MFA code storage backend cannot be reached.

    Attributes:
        None.
    """


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """
    Log a storage outage and re-raise it as a Garmin-store error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        GarminMFACodeStoreUnavailableError: Always raised.
    """
    logger.error(f"Garmin MFA code storage failed: {operation}", exc_info=err)
    raise GarminMFACodeStoreUnavailableError("Garmin MFA code storage is unavailable") from err


def _user_id_digest(user_id: int) -> str:
    """
    Hash a user ID for storage key names.

    Args:
        user_id: User ID to hash.

    Returns:
        SHA-256 hex digest for use in the storage key.

    Raises:
        None.
    """
    return core_hashing.sha256_hex(str(user_id))


class GarminMFACodeStore:
    """
    Temporary Garmin MFA code storage backed by the platform ``StateProvider``.

    Attributes:
        _state_override: Explicit provider (tests); ``None`` resolves the
            process-wide provider lazily at call time.
        _ttl_seconds: Code lifetime in seconds.
    """

    def __init__(self, state: StateProvider | None = None, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        """
        Initialize the Garmin MFA code store.

        Args:
            state: Optional explicit state provider (defaults to the process-wide one).
            ttl_seconds: How long each stored code remains valid.
        """
        self._state_override = state
        self._ttl_seconds = ttl_seconds

    @property
    def _state(self) -> StateProvider:
        return self._state_override if self._state_override is not None else platform_runtime.get_state()

    def _key(self, user_id: int) -> str:
        """Build the storage key for a user's pending MFA code."""
        return f"{_GARMIN_MFA_KEY_PREFIX}:{_user_id_digest(user_id)}"

    def add_code(self, user_id: int, code: str) -> None:
        """
        Store a Garmin MFA code with TTL.

        Args:
            user_id: Authenticated user ID.
            code: The MFA code submitted by the user.

        Raises:
            GarminMFACodeStoreUnavailableError: When storage is unavailable.
        """
        try:
            self._state.set(self._key(user_id), code.encode(), ttl_seconds=self._ttl_seconds)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("add Garmin MFA code", err)
        logger.debug(f"Stored Garmin MFA code for user {user_id}")

    def get_code(self, user_id: int) -> str | None:
        """
        Retrieve a Garmin MFA code.

        Args:
            user_id: Authenticated user ID.

        Returns:
            The stored code string, or None if missing or expired.

        Raises:
            GarminMFACodeStoreUnavailableError: When storage is unavailable.
        """
        try:
            value = self._state.get(self._key(user_id))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("get Garmin MFA code", err)
        return value.decode() if value is not None else None

    def delete_code(self, user_id: int) -> None:
        """
        Remove the Garmin MFA code for a user.

        Failures are swallowed because the entry expires via TTL anyway.

        Args:
            user_id: Authenticated user ID.

        Raises:
            None.
        """
        try:
            self._state.delete(self._key(user_id))
        except StateBackendUnavailableError as err:
            logger.warning("Failed to delete Garmin MFA code; entry will expire naturally via TTL", exc_info=err)

    def has_code(self, user_id: int) -> bool:
        """
        Return True when a non-expired code exists for a user.

        Args:
            user_id: Authenticated user ID.

        Returns:
            True if a valid code is stored, False otherwise.

        Raises:
            GarminMFACodeStoreUnavailableError: When storage is unavailable.
        """
        try:
            return self._state.get(self._key(user_id)) is not None
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("check Garmin MFA code", err)

    def clear_all(self) -> None:
        """
        Remove all Garmin MFA codes.

        Raises:
            GarminMFACodeStoreUnavailableError: When storage is unavailable.
        """
        try:
            self._state.delete_prefix(f"{_GARMIN_MFA_KEY_PREFIX}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable("clear Garmin MFA codes", err)


garmin_mfa_code_store = GarminMFACodeStore()


def get_garmin_mfa_code_store() -> GarminMFACodeStore:
    """
    Return the module-level Garmin MFA code store instance.

    Returns:
        The global :data:`garmin_mfa_code_store` singleton.

    Raises:
        None.
    """
    return garmin_mfa_code_store
