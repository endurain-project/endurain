"""Authentication security stores for login and MFA lockout.

Pending-login bookkeeping and progressive lockout counters are kept in the
platform ``StateProvider`` (an in-process dict under ``local``, Redis under
``distributed``). The atomic increment-and-lock step is delegated to
``StateProvider.record_tiered_failure`` — a single call that both backends
implement atomically — so this module no longer contains any Redis code or a
memory-vs-Redis split.
"""

from typing import NoReturn
from urllib.parse import unquote

from jasil.providers import StateBackendUnavailableError

import core.logger as core_logger
import modules.auth.lockout.contracts as auth_lockout_contracts
import modules.auth.lockout.integration_service as auth_lockout_integration

logger = core_logger.get_logger(__name__)

AuthSecurityStoreUnavailableError = auth_lockout_contracts.AuthSecurityStoreUnavailableError


def _raise_store_unavailable(operation: str, err: StateBackendUnavailableError) -> NoReturn:
    """Log a storage outage and re-raise it as an auth-security-store error.

    Args:
        operation: Storage operation that failed.
        err: The provider outage error.

    Raises:
        AuthSecurityStoreUnavailableError: Always raised.
    """
    logger.error(
        "Auth security storage failed: <operation>", exc_info=err, extra=core_logger.context(operation=operation)
    )
    raise AuthSecurityStoreUnavailableError("auth security storage is unavailable") from err


def normalize_username_key(username: str) -> str:
    """Normalise a username for security-store keys.

    Lockout counters must key on the same canonical form regardless of
    casing, surrounding whitespace, or URL-encoded variants supplied by
    the client.

    Args:
        username: Raw username string from the request.

    Returns:
        Canonical key suitable for lockout stores.

    Raises:
        None.
    """
    return unquote(username).replace("+", " ").strip().casefold()


def username_log_identifier(username: str) -> str:
    """Build a non-reversible username identifier for logs."""
    return auth_lockout_integration.username_log_identifier(username)
