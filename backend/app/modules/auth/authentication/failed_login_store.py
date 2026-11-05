"""Shared-state store for failed password login attempts."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from jasil.providers import StateProvider

import core.dependencies as core_dependencies
import core.network as core_network
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration


@dataclass(frozen=True)
class FailedLoginRecord:
    """The outcome of recording one failed password sign-in.

    Attributes:
        client_count: The failure count for the username and client network.
        account_locked_now: Whether this failure reached the account-wide cap and locked the account.
    """

    client_count: int
    account_locked_now: bool


@runtime_checkable
class FailedLoginStore(Protocol):
    """Operations supported by the failed-login lockout store."""

    def is_locked_out(self, username: str, ip_address: str, *, known_device: bool = False) -> bool:
        """Return whether the username is locked out for the client network or account-wide."""
        ...

    def get_lockout_time(self, username: str, ip_address: str, *, known_device: bool = False) -> datetime | None:
        """Return the active lockout expiry, if one exists; a known device is not held by the account-wide lock."""
        ...

    def record_failed_attempt(self, username: str, ip_address: str) -> FailedLoginRecord:
        """Record a failed attempt against the username and client network and the account."""
        ...

    def reset_attempts(self, username: str, ip_address: str) -> None:
        """Clear the failed-attempt counts for the username and client network, and the account's."""
        ...

    def reset_account(self, username: str) -> None:
        """Clear the account-wide failed-attempt count and lock of the username."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...


class FailedLoginAttempts:
    """Track failed logins using the shared platform state provider.

    Failures count per username and client network (an IPv6 address by its /64), so one client cannot lock an account
    for everyone. A second, much higher count of failures in a row locks the account across every address, except for
    a known device of the account.
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
            attempts_ttl_seconds=lockout_contracts.ACCOUNT_LOGIN_ATTEMPTS_TTL_SECONDS,
            normalize_key=lockout_integration.normalize_username_key,
        )

    @classmethod
    def _client_key(cls, username: str, ip_address: str) -> str:
        """Build the per-client key; a network never contains ``|``, so the pair cannot be forged by a username."""
        return f"{lockout_integration.normalize_username_key(username)}|{core_network.client_network(ip_address)}"

    def is_locked_out(self, username: str, ip_address: str, *, known_device: bool = False) -> bool:
        """Check if a username is locked out for this client network or, unless a known device, account-wide."""
        return self.get_lockout_time(username, ip_address, known_device=known_device) is not None

    def get_lockout_time(self, username: str, ip_address: str, *, known_device: bool = False) -> datetime | None:
        """Return the later of the client and account-wide lockout expiries; a known device ignores the latter."""
        expiries = (
            self._by_client.get_lockout_time(self._client_key(username, ip_address)),
            None if known_device else self._by_account.get_lockout_time(username),
        )
        return max((expiry for expiry in expiries if expiry is not None), default=None)

    def record_failed_attempt(self, username: str, ip_address: str) -> FailedLoginRecord:
        """Record a failed login against the username and client network and against the account."""
        account = self._by_account.record_failure(username)
        client = self._by_client.record_failure(self._client_key(username, ip_address))
        return FailedLoginRecord(client_count=client.count, account_locked_now=account.newly_locked)

    def reset_attempts(self, username: str, ip_address: str) -> None:
        """Clear the failed-login counters for the username and client network, and the account's."""
        self._by_client.reset_attempts(self._client_key(username, ip_address))
        self.reset_account(username)

    def reset_account(self, username: str) -> None:
        """Clear the account-wide failed-login count and lock of the username."""
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
