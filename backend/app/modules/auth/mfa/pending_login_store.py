"""Shared state for pending MFA login challenges."""

import secrets
from datetime import datetime
from typing import NoReturn, Protocol, runtime_checkable

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.dependencies as core_dependencies
import core.hashing as core_hashing
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.mfa.totp_replay_store as mfa_totp_replay_store

_PENDING_MFA_KEY_PREFIX = "endurain:auth:mfa:pending"
_PENDING_MFA_TTL_SECONDS = 300

AuthSecurityStoreUnavailableError = lockout_contracts.AuthSecurityStoreUnavailableError


@runtime_checkable
class PendingMFAStore(Protocol):
    """Contract for pending login and MFA lockout state."""

    def add_pending_login(self, user_id: int) -> str:
        """Start a pending login and return the challenge that names it."""
        ...

    def get_pending_login(self, challenge: str) -> int | None:
        """Return the user a challenge names, if it is still pending."""
        ...

    def claim_pending_login(self, challenge: str) -> int | None:
        """Atomically end a pending login and return its user."""
        ...

    def delete_pending_login(self, challenge: str) -> None:
        """Abandon a pending login."""
        ...

    def clear_for_user(self, user_id: int) -> int:
        """Implement the clear for user operation."""
        ...

    def claim_totp_step(self, user_id: int, step: int) -> bool:
        """Record an accepted TOTP step as used; False when it already was."""
        ...

    def is_locked_out(self, username: str) -> bool:
        """Return whether the supplied key is currently locked out."""
        ...

    def get_lockout_time(self, username: str) -> datetime | None:
        """Return the active lockout expiry, if one exists."""
        ...

    def record_failed_attempt(self, username: str) -> int:
        """Record a failed attempt and return the updated count."""
        ...

    def reset_attempts(self, username: str) -> None:
        """Clear the failed-attempt count for the supplied key."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...


def _raise_store_unavailable(err: StateBackendUnavailableError) -> NoReturn:
    """Translate a state-provider outage into the auth store error."""
    raise AuthSecurityStoreUnavailableError("auth security storage is unavailable") from err


class PendingMFALogin:
    """Store pending MFA logins and their progressive failure lockout."""

    def __init__(self, state: StateProvider) -> None:
        """Bind the store to a platform state provider."""
        self._state = state
        self._lockout = lockout_integration.new_progressive_lockout(
            state,
            name="mfa",
            tiers=lockout_contracts.MFA_LOCKOUT_TIERS,
            attempts_ttl_seconds=2 * 60 * 60,
            normalize_key=lockout_integration.normalize_username_key,
        )

    @staticmethod
    def _pending_key(challenge: str) -> str:
        """Build the key for a pending MFA login from a digest of its challenge, so the store never holds it."""
        return f"{_PENDING_MFA_KEY_PREFIX}:{core_hashing.sha256_hex(challenge)}"

    def add_pending_login(self, user_id: int) -> str:
        """Start a pending login for five minutes and return the unguessable challenge that names it.

        The challenge, not the username, names the login, so only the client that signed in can submit its
        codes, and nobody who merely knows a username can try codes or lock the account out.
        """
        challenge = secrets.token_urlsafe(32)
        try:
            self._state.set(self._pending_key(challenge), str(user_id).encode(), ttl_seconds=_PENDING_MFA_TTL_SECONDS)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return challenge

    def get_pending_login(self, challenge: str) -> int | None:
        """Return the pending user ID, removing a corrupt entry."""
        key = self._pending_key(challenge)
        try:
            value = self._state.get(key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        if value is None:
            return None
        try:
            return int(value.decode())
        except (TypeError, ValueError):
            try:
                self._state.delete(key)
            except StateBackendUnavailableError as err:
                _raise_store_unavailable(err)
            return None

    def claim_pending_login(self, challenge: str) -> int | None:
        """Atomically retrieve and remove a pending login."""
        try:
            value = self._state.get_and_delete(self._pending_key(challenge))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        if value is None:
            return None
        try:
            return int(value.decode())
        except (TypeError, ValueError):
            return None

    def delete_pending_login(self, challenge: str) -> None:
        """Remove a pending login."""
        try:
            self._state.delete(self._pending_key(challenge))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)

    def clear_for_user(self, user_id: int) -> int:
        """Remove pending MFA logins for a user."""
        target = str(user_id).encode()
        removed = 0
        try:
            for key in list(self._state.iter_keys(f"{_PENDING_MFA_KEY_PREFIX}:")):
                if self._state.get(key) == target:
                    self._state.delete(key)
                    removed += 1
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return removed

    def claim_totp_step(self, user_id: int, step: int) -> bool:
        """Record an accepted TOTP step as used; False when it already was."""
        return mfa_totp_replay_store.claim_totp_step(self._state, user_id, step)

    def is_locked_out(self, username: str) -> bool:
        """Return whether MFA attempts are locked for a username."""
        return self._lockout.is_locked_out(username)

    def get_lockout_time(self, username: str) -> datetime | None:
        """Return the lockout expiry for a username."""
        return self._lockout.get_lockout_time(username)

    def record_failed_attempt(self, username: str) -> int:
        """Record an MFA failure and return the attempt count."""
        return self._lockout.record_failed_attempt(username)

    def reset_attempts(self, username: str) -> None:
        """Reset MFA failures after a successful challenge."""
        self._lockout.reset_attempts(username)

    def clear_all(self) -> None:
        """Clear pending challenges and MFA failure counters."""
        try:
            self._state.delete_prefix(f"{_PENDING_MFA_KEY_PREFIX}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        self._lockout.clear_all()


def get_pending_mfa_store(
    state: core_dependencies.PlatformState,
) -> PendingMFAStore:
    """Build the pending-MFA store from the active platform state provider."""
    return PendingMFALogin(state)


def clear_pending_mfa_for_user(state: StateProvider, user_id: int) -> int:
    """Remove pending MFA logins after credential changes, tolerating provider outages."""
    try:
        return PendingMFALogin(state).clear_for_user(user_id)
    except AuthSecurityStoreUnavailableError:
        return 0
