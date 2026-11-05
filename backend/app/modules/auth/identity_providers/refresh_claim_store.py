"""Claims that keep one refresh of an identity-provider token running at a time.

Two refreshes of the same session's token would present the same refresh token to the provider; one that rotates tokens
rejects the second, and one with reuse detection revokes the whole session. The claim lives in the platform
``StateProvider``, so it holds across replicas and workers.
"""

import jasil.providers as platform_providers

import core.hashing as core_hashing
import core.logger as core_logger
import modules.auth.identity_providers.constants as idp_constants

logger = core_logger.get_logger(__name__)

_CLAIM_KEY = "endurain:idp:token-refresh:{session_id}"


class IdpRefreshClaimStore:
    """Per-session refresh claims backed by the platform ``StateProvider``."""

    def __init__(self, state: platform_providers.StateProvider) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
        """
        self._state = state

    def claim(self, session_id: str) -> bool:
        """Claim the right to refresh one session's token.

        Fails open when the state is unreachable: the refresh writes only over the token it read, so a race
        cannot lose a newer token, whereas failing closed would stop every refresh during the outage.

        Args:
            session_id: The session whose token is refreshed.

        Returns:
            True when this caller may refresh, False when another refresh holds the claim.
        """
        try:
            return self._state.set_if_absent(
                _CLAIM_KEY.format(session_id=session_id), b"1", idp_constants.TOKEN_REFRESH_CLAIM_TTL_SECONDS
            )
        except platform_providers.StateBackendUnavailableError as err:
            logger.warning(
                "Could not claim the identity-provider token refresh; refreshing anyway",
                exc_info=err,
                extra=core_logger.context(session_id=core_hashing.log_fingerprint(session_id)),
            )
            return True

    def release(self, session_id: str) -> None:
        """Release a session's refresh claim, so the next refresh need not wait for it to expire.

        Args:
            session_id: The session whose claim to release.
        """
        try:
            self._state.delete(_CLAIM_KEY.format(session_id=session_id))
        except platform_providers.StateBackendUnavailableError as err:
            logger.warning(
                "Could not release the identity-provider token refresh claim; it expires on its own",
                exc_info=err,
                extra=core_logger.context(session_id=core_hashing.log_fingerprint(session_id)),
            )
