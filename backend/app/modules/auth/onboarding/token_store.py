"""Shared state for the one-time setup tokens that gate first-run onboarding."""

import secrets
from typing import NoReturn

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.exceptions as core_exceptions
import core.hashing as core_hashing

_KEY_PREFIX = "endurain:auth:onboarding:token"

#: How long a setup token stays valid; a restart prints a fresh one.
TOKEN_TTL_SECONDS = 24 * 60 * 60


def _raise_store_unavailable(err: StateBackendUnavailableError) -> NoReturn:
    """Translate a state-provider outage into the error that answers 503."""
    raise core_exceptions.ServiceUnavailableError("Onboarding storage is unavailable") from err


class OnboardingTokenStore:
    """Issue, check and consume setup tokens over the platform state provider.

    Only the SHA-256 digest of a token forms its key, so the store never holds a token a reader could use.
    """

    def __init__(self, state: StateProvider) -> None:
        """Bind the store to a platform state provider.

        Args:
            state: The platform state provider.
        """
        self._state = state

    @staticmethod
    def _key(token: str) -> str:
        """Build the key of a token from its digest."""
        return f"{_KEY_PREFIX}:{core_hashing.sha256_hex(token)}"

    def issue(self) -> str:
        """Mint a setup token that stays valid for ``TOKEN_TTL_SECONDS``.

        Returns:
            The raw token, which the caller shows to the operator and never stores.

        Raises:
            ServiceUnavailableError: If the state backend is unavailable.
        """
        token = secrets.token_urlsafe(32)
        try:
            self._state.set(self._key(token), b"1", ttl_seconds=TOKEN_TTL_SECONDS)
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
        return token

    def exists(self, token: str) -> bool:
        """Tell whether a token is still valid, without consuming it.

        Args:
            token: The token a client sent.

        Returns:
            True when the token was issued and has neither expired nor been claimed.

        Raises:
            ServiceUnavailableError: If the state backend is unavailable.
        """
        try:
            return self._state.get(self._key(token)) is not None
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)

    def claim(self, token: str) -> bool:
        """Atomically consume a token.

        Args:
            token: The token a client sent.

        Returns:
            True for the one caller that consumed it; False when it was unknown, expired or already claimed.

        Raises:
            ServiceUnavailableError: If the state backend is unavailable.
        """
        try:
            return self._state.get_and_delete(self._key(token)) is not None
        except StateBackendUnavailableError as err:
            _raise_store_unavailable(err)
