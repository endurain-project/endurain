"""Shared-state store for failed password login attempts."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from jasil.providers import StateProvider

import core.dependencies as core_dependencies
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration


@runtime_checkable
class FailedLoginStore(Protocol):
    """Operations supported by the failed-login lockout store."""

    def is_locked_out(self, username: str, ip_address: str) -> bool:
        """Return whether the username is locked out for the client address or account-wide."""
        ...

    def get_lockout_time(self, username: str, ip_address: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        ...

    def record_failed_attempt(self, username: str, ip_address: str) -> int:
        """Record a failed attempt and return the count for the username and client address."""
        ...

    def reset_attempts(self, username: str, ip_address: str) -> None:
        """Clear the failed-attempt counts for the username and client address."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...


class FailedLoginAttempts:
    """Track failed logins using the shared platform state provider.

    Failures count per username and client address, so one client cannot lock an account for everyone. A second,
    much higher account-wide threshold still stops a brute force spread over many addresses.
    """

    def __init__(self, state: StateProvider) -> None:
        """Bind failed-login tracking to the shared platform state provider."""
        self._by_client = lockout_integration.new_progressive_lockout(
            state,
            name="login",
            tiers=lockout_contracts.LOGIN_LOCKOUT_TIERS,
            attempts_ttl_seconds=24 * 60 * 60,
        )
        self._by_account = lockout_integration.new_progressive_lockout(
            state,
            name="login_account",
            tiers=lockout_contracts.ACCOUNT_LOGIN_LOCKOUT_TIERS,
            attempts_ttl_seconds=60 * 60,
            normalize_key=lockout_integration.normalize_username_key,
        )

    @staticmethod
    def _client_key(username: str, ip_address: str) -> str:
        """Build the per-client key; an address never contains ``|``, so the pair cannot be forged by a username."""
        return f"{lockout_integration.normalize_username_key(username)}|{ip_address}"

    def is_locked_out(self, username: str, ip_address: str) -> bool:
        """Check if a username is locked out for this client address or account-wide."""
        return self.get_lockout_time(username, ip_address) is not None

    def get_lockout_time(self, username: str, ip_address: str) -> datetime | None:
        """Return the later of the client and account-wide lockout expiries, if any."""
        expiries = (
            self._by_client.get_lockout_time(self._client_key(username, ip_address)),
            self._by_account.get_lockout_time(username),
        )
        return max((expiry for expiry in expiries if expiry is not None), default=None)

    def record_failed_attempt(self, username: str, ip_address: str) -> int:
        """Record a failed login and return the attempt count for the username and client address."""
        self._by_account.record_failed_attempt(username)
        return self._by_client.record_failed_attempt(self._client_key(username, ip_address))

    def reset_attempts(self, username: str, ip_address: str) -> None:
        """Clear the failed-login counters for the username and client address."""
        self._by_client.reset_attempts(self._client_key(username, ip_address))
        self._by_account.reset_attempts(username)

    def clear_all(self) -> None:
        """Clear all failed-login records."""
        self._by_client.clear_all()
        self._by_account.clear_all()


def get_failed_login_attempts(
    state: core_dependencies.PlatformState,
) -> FailedLoginStore:
    """Provide a failed-login store bound to the active platform state."""
    return FailedLoginAttempts(state)
