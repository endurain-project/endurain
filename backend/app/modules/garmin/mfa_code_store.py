"""Temporary Garmin MFA code storage for cross-request handoff.

The code is a live credential, so it is encrypted before it is stored.

The Garmin Connect link flow is asynchronous: the backend starts a blocking
login in a thread that eventually calls back for an MFA code, while the user
submits that code via a separate HTTP request.  In a multi-worker deployment
these two requests may land on different processes, so the code is kept in the
platform ``StateProvider`` (an in-process dict under ``local``, Redis under
``distributed``).

Interface::

    add_code(user_id, code)   - store the MFA code for user_id
    get_code(user_id)         - retrieve it (does NOT delete)
    delete_code(user_id)      - remove it after consumption
"""

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.attempt_state as core_attempt_state
import core.cryptography as core_cryptography
import core.logger as core_logger
import modules.garmin.constants as garmin_constants

logger = core_logger.get_logger(__name__)

# TTL must exceed the MFA_WAIT_SECONDS a login waits for a code.
_DEFAULT_TTL_SECONDS: int = garmin_constants.MFA_WAIT_SECONDS + 30


def _encrypt(code: str) -> bytes:
    """Encrypt an MFA code, a live credential, before it reaches shared state.

    Args:
        code: The MFA code submitted by the user.

    Returns:
        The encrypted code.
    """
    return (core_cryptography.encrypt_token_fernet(code) or "").encode()


class GarminMFACodeStore:
    """Temporary Garmin MFA code storage backed by the platform ``StateProvider``.

    Attributes:
        _state: The platform state provider.
        _ttl_seconds: Code lifetime in seconds.
    """

    def __init__(self, state: StateProvider, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        """Initialize the Garmin MFA code store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long each stored code remains valid.
        """
        self._state = state
        self._ttl_seconds = ttl_seconds

    def _key(self, user_id: int) -> str:
        """Build the storage key for a user's pending MFA code."""
        return core_attempt_state.key("garmin", "mfa:code", str(user_id))

    def add_code(self, user_id: int, code: str) -> None:
        """Store a Garmin MFA code with TTL.

        Args:
            user_id: Authenticated user ID.
            code: The MFA code submitted by the user.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            self._state.set(self._key(user_id), _encrypt(code), ttl_seconds=self._ttl_seconds)
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("add Garmin MFA code", err)
        logger.debug(
            "Stored Garmin MFA code",
            extra=core_logger.context(user_id=user_id),
        )

    def get_code(self, user_id: int) -> str | None:
        """Retrieve a Garmin MFA code.

        Args:
            user_id: Authenticated user ID.

        Returns:
            The stored code string, or None if missing or expired.

        Raises:
            StateUnavailableError: When storage is unavailable.
            CryptographyError: When the stored code cannot be decrypted.
        """
        try:
            value = self._state.get(self._key(user_id))
        except StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("get Garmin MFA code", err)
        return core_cryptography.decrypt_token_fernet(value.decode()) if value is not None else None

    def delete_code(self, user_id: int) -> None:
        """Remove the Garmin MFA code for a user.

        Failures are swallowed because the entry expires via TTL anyway.

        Args:
            user_id: Authenticated user ID.
        """
        try:
            self._state.delete(self._key(user_id))
        except StateBackendUnavailableError as err:
            logger.warning("Failed to delete Garmin MFA code; entry will expire naturally via TTL", exc_info=err)
