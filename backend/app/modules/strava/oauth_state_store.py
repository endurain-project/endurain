"""The one-time state that ties a Strava OAuth callback to the user who started it.

The browser stores a random state before sending the user to Strava and hands it back with the
authorization code. The state is held per user with a short lifetime and is consumed by the first
attempt to use it, so a leaked or replayed callback cannot link anything. It lives in the platform
``StateProvider``, so the callback may land on any replica.

Interface::

    begin(user_id, state)      - store the state, replacing any earlier one
    consume(user_id, state)    - True once for the stored state, then never again
    clear(user_id)             - forget the state
"""

import hmac

import jasil.providers as platform_providers

import core.attempt_state as core_attempt_state
import core.logger as core_logger
import modules.strava.constants as strava_constants

logger = core_logger.get_logger(__name__)


class StravaOAuthStateStore:
    """Strava OAuth state backed by the platform ``StateProvider``.

    Attributes:
        _state: The platform state provider.
        _ttl_seconds: How long a stored state stays valid.
    """

    def __init__(
        self, state: platform_providers.StateProvider, ttl_seconds: int = strava_constants.OAUTH_STATE_TTL_SECONDS
    ) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
            ttl_seconds: How long a stored state stays valid.
        """
        self._state = state
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _key(user_id: int) -> str:
        return core_attempt_state.key("strava", "oauth_state", str(user_id))

    def begin(self, user_id: int, state: str) -> None:
        """Store the state a user is about to round-trip through Strava.

        Args:
            user_id: The authenticated user.
            state: The opaque state.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            self._state.set(self._key(user_id), state.encode(), ttl_seconds=self._ttl_seconds)
        except platform_providers.StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("begin strava:oauth_state", err)

    def consume(self, user_id: int, state: str) -> bool:
        """Check a returned state against the stored one and use it up.

        The stored state is deleted whether or not it matches, so a wrong guess cannot be retried.

        Args:
            user_id: The authenticated user.
            state: The state Strava returned.

        Returns:
            True when it matches the user's unexpired state.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            stored = self._state.get_and_delete(self._key(user_id))
        except platform_providers.StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("consume strava:oauth_state", err)
        return stored is not None and hmac.compare_digest(stored, state.encode())

    def clear(self, user_id: int) -> None:
        """Forget a user's stored state.

        Args:
            user_id: The authenticated user.

        Raises:
            StateUnavailableError: When storage is unavailable.
        """
        try:
            self._state.delete(self._key(user_id))
        except platform_providers.StateBackendUnavailableError as err:
            core_attempt_state.raise_unavailable("clear strava:oauth_state", err)
