"""Shared state for the pending password changes of sign-ins whose password an administrator set."""

import secrets
from typing import NoReturn, Protocol, runtime_checkable

from jasil.providers import StateBackendUnavailableError, StateProvider
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr, ValidationError

import core.dependencies as core_dependencies
import core.hashing as core_hashing
import modules.auth.constants as auth_constants
import modules.auth.lockout.contracts as lockout_contracts

_PENDING_CHANGE_KEY_PREFIX = "endurain:auth:password_change:pending"
_PENDING_CHANGE_TTL_SECONDS = 600

AuthSecurityStoreUnavailableError = lockout_contracts.AuthSecurityStoreUnavailableError


class PendingPasswordChange(BaseModel):
    """A sign-in that has proven the password (and the second factor) and waits for the new password.

    Attributes:
        user_id: The account that signed in.
        client_type: The client type of the sign-in; the password-change step must come from the same kind.
        code_challenge: The PKCE code challenge the sign-in carried, if any.
        code_challenge_method: The PKCE challenge method the sign-in carried, if any.
        mfa: Whether a second factor was verified for the sign-in, for its audit row.
        security_generation: The account's security generation when the challenge was issued; the change is accepted
            only while it is still current. An entry written without one is refused.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: StrictInt
    client_type: auth_constants.ClientType
    code_challenge: StrictStr | None
    code_challenge_method: StrictStr | None
    mfa: StrictBool
    security_generation: StrictInt | None = None


@runtime_checkable
class PendingPasswordChangeStore(Protocol):
    """Contract for pending password changes."""

    def add(self, pending: PendingPasswordChange) -> str:
        """Start a pending password change and return the challenge that names it."""
        ...

    def get(self, challenge: str) -> PendingPasswordChange | None:
        """Return the pending password change a challenge names, if it is still pending."""
        ...

    def claim(self, challenge: str) -> PendingPasswordChange | None:
        """Atomically end a pending password change and return it."""
        ...


def _raise_store_unavailable(err: StateBackendUnavailableError) -> NoReturn:
    """Translate a state-provider outage into the auth store error."""
    raise AuthSecurityStoreUnavailableError("auth security storage is unavailable") from err


def _decode(value: bytes) -> PendingPasswordChange | None:
    """Return the stored record, or None when it cannot be read."""
    try:
        return PendingPasswordChange.model_validate_json(value)
    except ValidationError:
        return None


class PendingPasswordChanges:
    """Store pending password changes in the shared platform state."""

    def __init__(self, state: StateProvider) -> None:
        """Bind the store to a platform state provider."""
        self._state = state

    @staticmethod
    def _key(challenge: str) -> str:
        """Build the key for a pending change from a digest of its challenge, so the store never holds it."""
        return f"{_PENDING_CHANGE_KEY_PREFIX}:{core_hashing.sha256_hex(challenge)}"

    def add(self, pending: PendingPasswordChange) -> str:
        """Start a pending password change for ten minutes and return the unguessable challenge that names it.

        The challenge, not the username, names the sign-in, so only the client that proved the password can choose
        the new one.
        """
        challenge = secrets.token_urlsafe(32)
        try:
            self._state.set(
                self._key(challenge),
                pending.model_dump_json().encode(),
                ttl_seconds=_PENDING_CHANGE_TTL_SECONDS,
            )
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return challenge

    def get(self, challenge: str) -> PendingPasswordChange | None:
        """Return the pending password change, removing a corrupt entry."""
        key = self._key(challenge)
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

    def claim(self, challenge: str) -> PendingPasswordChange | None:
        """Atomically retrieve and remove a pending password change."""
        try:
            value = self._state.get_and_delete(self._key(challenge))
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return None if value is None else _decode(value)


def get_pending_password_change_store(state: core_dependencies.PlatformState) -> PendingPasswordChangeStore:
    """Build the pending-password-change store from the active platform state provider."""
    return PendingPasswordChanges(state)
