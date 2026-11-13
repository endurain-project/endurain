"""Shared state for pending MFA login challenges."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, Protocol, runtime_checkable

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, ValidationError

import core.dependencies as core_dependencies
import core.hashing as core_hashing
import core.network as core_network
import modules.auth.constants as auth_constants
import modules.auth.lockout.contracts as lockout_contracts
import modules.auth.lockout.integration_service as lockout_integration
import modules.auth.mfa.totp_replay_store as mfa_totp_replay_store

_PENDING_MFA_KEY_PREFIX = "endurain:auth:mfa:pending"
_CHALLENGE_ATTEMPTS_KEY_PREFIX = "endurain:auth:mfa:challenge-attempts"
_PENDING_MFA_TTL_SECONDS = 300

#: Wrong codes one challenge takes before it ends and the client must sign in again.
MFA_CHALLENGE_MAX_ATTEMPTS = 3

AuthSecurityStoreUnavailableError = lockout_contracts.AuthSecurityStoreUnavailableError


class PendingLogin(BaseModel):
    """A password sign-in that has proven the password and waits for its second factor.

    Attributes:
        user_id: The account that signed in.
        client_type: The client type of the password step; the MFA step must come from the same kind.
        code_challenge: The PKCE code challenge of the password step; a mobile sign-in always carries one.
        code_challenge_method: The PKCE challenge method of the password step.
        client_network: The client network of the password step (an IPv4 address or an IPv6 /64); the MFA step is
            accepted only from it.
        security_generation: The account's security generation when the password step succeeded; the MFA step is
            accepted only while it is still current. An entry written without one is refused.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: uuid.UUID
    client_type: auth_constants.ClientType
    code_challenge: StrictStr | None
    code_challenge_method: StrictStr | None
    client_network: StrictStr
    security_generation: StrictInt | None = None


@dataclass(frozen=True)
class FailedMfaRecord:
    """The outcome of recording one wrong MFA code.

    Attributes:
        count: The wrong-code count of the tiered lock after this code.
        account_locked_now: Whether this code reached the account-wide cap and locked the account.
    """

    count: int
    account_locked_now: bool


@runtime_checkable
class PendingMFAStore(Protocol):
    """Contract for pending login and MFA lockout state."""

    def add_pending_login(self, pending: PendingLogin) -> str:
        """Start a pending login and return the challenge that names it."""
        ...

    def get_pending_login(self, challenge: str) -> PendingLogin | None:
        """Return the pending login a challenge names, if it is still pending."""
        ...

    def claim_pending_login(self, challenge: str) -> PendingLogin | None:
        """Atomically end a pending login and return it."""
        ...

    def delete_pending_login(self, challenge: str) -> None:
        """Abandon a pending login."""
        ...

    def record_wrong_code(self, challenge: str) -> bool:
        """Count a wrong code against a challenge; True when it was the last one the challenge allows."""
        ...

    def claim_totp_step(self, user_id: uuid.UUID, step: int) -> bool:
        """Record an accepted TOTP step as used; False when it already was."""
        ...

    def is_locked_out(self, username: str, ip_address: str, *, user_id: uuid.UUID, known_device: bool = False) -> bool:
        """Return whether the account is locked out for this client network or account-wide."""
        ...

    def get_lockout_time(
        self, username: str, ip_address: str, *, user_id: uuid.UUID, known_device: bool = False
    ) -> datetime | None:
        """Return the active lockout expiry, if one exists; a known device is not held by the account-wide lock."""
        ...

    def record_failed_attempt(self, username: str, ip_address: str, *, user_id: uuid.UUID) -> FailedMfaRecord:
        """Record a wrong code against the username and client network and against the account."""
        ...

    def reset_attempts(self, username: str, ip_address: str, *, user_id: uuid.UUID) -> None:
        """Clear the failed-attempt counts of the username and client network, and the account's."""
        ...

    def reset_account(self, user_id: uuid.UUID) -> None:
        """Clear the account-wide failed-attempt count and lock of the account."""
        ...

    def clear_all(self) -> None:
        """Clear all tracked lockout attempts."""
        ...


def _raise_store_unavailable(err: StateBackendUnavailableError) -> NoReturn:
    """Translate a state-provider outage into the auth store error."""
    raise AuthSecurityStoreUnavailableError("auth security storage is unavailable") from err


def _decode(value: bytes) -> PendingLogin | None:
    """Return the stored record, or None when it cannot be read."""
    try:
        return PendingLogin.model_validate_json(value)
    except ValidationError:
        return None


class PendingMFALogin:
    """Store pending MFA logins and their progressive failure lockouts.

    Wrong codes count per username and client network (an IPv6 address by its /64) toward a tiered lock that always
    applies, so one client cannot lock the owner out for everyone. They also count toward a much higher account-wide
    count, keyed by the user id so a username change cannot drop it, that locks the account across every network,
    except for a known device of the account.
    """

    def __init__(self, state: StateProvider) -> None:
        """Bind the store to a platform state provider."""
        self._state = state
        self._lockout = lockout_integration.new_progressive_lockout(
            state,
            name="mfa",
            tiers=lockout_contracts.MFA_LOCKOUT_TIERS,
            attempts_ttl_seconds=2 * 60 * 60,
        )
        self._by_account = lockout_integration.new_progressive_lockout(
            state,
            name="mfa_account",
            tiers=lockout_contracts.ACCOUNT_MFA_LOCKOUT_TIERS,
            attempts_ttl_seconds=lockout_contracts.ACCOUNT_MFA_ATTEMPTS_TTL_SECONDS,
        )

    @staticmethod
    def _client_key(username: str, ip_address: str) -> str:
        """Build the per-client key; a network never contains ``|``, so the pair cannot be forged by a username."""
        return f"{lockout_integration.normalize_username_key(username)}|{core_network.client_network(ip_address)}"

    @staticmethod
    def _pending_key(challenge: str) -> str:
        """Build the key for a pending MFA login from a digest of its challenge, so the store never holds it."""
        return f"{_PENDING_MFA_KEY_PREFIX}:{core_hashing.sha256_hex(challenge)}"

    @staticmethod
    def _attempts_key(challenge: str) -> str:
        """Build the key for a challenge's wrong-code count from a digest of the challenge."""
        return f"{_CHALLENGE_ATTEMPTS_KEY_PREFIX}:{core_hashing.sha256_hex(challenge)}"

    def add_pending_login(self, pending: PendingLogin) -> str:
        """Start a pending login for five minutes and return the unguessable challenge that names it.

        The challenge, not the username, names the login, so only the client that signed in can submit its
        codes, and nobody who merely knows a username can try codes or lock the account out.
        """
        challenge = secrets.token_urlsafe(32)
        try:
            self._state.set(
                self._pending_key(challenge), pending.model_dump_json().encode(), ttl_seconds=_PENDING_MFA_TTL_SECONDS
            )
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return challenge

    def get_pending_login(self, challenge: str) -> PendingLogin | None:
        """Return the pending login, removing a corrupt entry."""
        key = self._pending_key(challenge)
        try:
            value = self._state.get(key)
            if value is None:
                return None
            pending = _decode(value)
            if pending is None:
                self._state.delete(key)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return pending

    def claim_pending_login(self, challenge: str) -> PendingLogin | None:
        """Atomically retrieve and remove a pending login, and the wrong-code count of its challenge."""
        try:
            value = self._state.get_and_delete(self._pending_key(challenge))
            self._state.delete(self._attempts_key(challenge))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return None if value is None else _decode(value)

    def delete_pending_login(self, challenge: str) -> None:
        """Remove a pending login."""
        try:
            self._state.delete(self._pending_key(challenge))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)

    def record_wrong_code(self, challenge: str) -> bool:
        """Count a wrong code against a challenge and end the challenge once it has taken the allowed number.

        The count lives under its own key prefix and expires with the challenge.

        Args:
            challenge: The challenge the wrong code was presented with.

        Returns:
            True when this was the last wrong code the challenge allows and the challenge has ended.

        Raises:
            AuthSecurityStoreUnavailableError: If the state provider is unavailable.
        """
        try:
            attempts = self._state.incr(self._attempts_key(challenge), ttl_seconds=_PENDING_MFA_TTL_SECONDS)
            if attempts < MFA_CHALLENGE_MAX_ATTEMPTS:
                return False
            self._state.delete(self._pending_key(challenge))
            self._state.delete(self._attempts_key(challenge))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return True

    def claim_totp_step(self, user_id: uuid.UUID, step: int) -> bool:
        """Record an accepted TOTP step as used; False when it already was."""
        return mfa_totp_replay_store.claim_totp_step(self._state, user_id, step)

    def is_locked_out(self, username: str, ip_address: str, *, user_id: uuid.UUID, known_device: bool = False) -> bool:
        """Return whether MFA is locked for the account on this network or, unless a known device, account-wide."""
        return self.get_lockout_time(username, ip_address, user_id=user_id, known_device=known_device) is not None

    def get_lockout_time(
        self, username: str, ip_address: str, *, user_id: uuid.UUID, known_device: bool = False
    ) -> datetime | None:
        """Return the later of the client and account-wide lockout expiries; a known device ignores the latter."""
        expiries = (
            self._lockout.get_lockout_time(self._client_key(username, ip_address)),
            None if known_device else self._by_account.get_lockout_time(str(user_id)),
        )
        return max((expiry for expiry in expiries if expiry is not None), default=None)

    def record_failed_attempt(self, username: str, ip_address: str, *, user_id: uuid.UUID) -> FailedMfaRecord:
        """Record a wrong MFA code against the account and against the tiered counter of the client network."""
        account = self._by_account.record_failure(str(user_id))
        tiered = self._lockout.record_failure(self._client_key(username, ip_address))
        return FailedMfaRecord(count=tiered.count, account_locked_now=account.newly_locked)

    def reset_attempts(self, username: str, ip_address: str, *, user_id: uuid.UUID) -> None:
        """Reset the client network's and the account-wide MFA failure counts after a successful challenge."""
        self._lockout.reset_attempts(self._client_key(username, ip_address))
        self.reset_account(user_id)

    def reset_account(self, user_id: uuid.UUID) -> None:
        """Clear the account-wide MFA failure count and lock of the account."""
        self._by_account.reset_attempts(str(user_id))

    def clear_all(self) -> None:
        """Clear pending challenges, their wrong-code counts and MFA failure counters."""
        try:
            self._state.delete_prefix(f"{_PENDING_MFA_KEY_PREFIX}:")
            self._state.delete_prefix(f"{_CHALLENGE_ATTEMPTS_KEY_PREFIX}:")
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        self._lockout.clear_all()
        self._by_account.clear_all()


def get_pending_mfa_store(
    state: core_dependencies.PlatformState,
) -> PendingMFAStore:
    """Build the pending-MFA store from the active platform state provider."""
    return PendingMFALogin(state)
