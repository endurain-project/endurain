"""Claims that keep one refresh of an identity-provider token running at a time.

Two refreshes of the same link would present the same refresh token to the provider; one that rotates tokens
rejects the second, and one with reuse detection revokes the whole session. The claim lives in the platform
``StateProvider``, so it holds across replicas and workers.
"""

import jasil.providers as platform_providers

import core.logger as core_logger
import modules.auth.identity_providers.constants as idp_constants

logger = core_logger.get_logger(__name__)

_CLAIM_KEY = "endurain:idp:token-refresh:{user_id}:{idp_id}"


class IdpRefreshClaimStore:
    """Per-link refresh claims backed by the platform ``StateProvider``."""

    def __init__(self, state: platform_providers.StateProvider) -> None:
        """Initialize the store.

        Args:
            state: The platform state provider.
        """
        self._state = state

    def claim(self, user_id: int, idp_id: int) -> bool:
        """Claim the right to refresh one link's token.

        Fails open when the state is unreachable: the refresh writes only over the token it read, so a race
        cannot lose a newer token, whereas failing closed would stop every refresh during the outage.

        Args:
            user_id: The link's user.
            idp_id: The link's provider.

        Returns:
            True when this caller may refresh, False when another refresh holds the claim.
        """
        try:
            return self._state.set_if_absent(
                _CLAIM_KEY.format(user_id=user_id, idp_id=idp_id), b"1", idp_constants.TOKEN_REFRESH_CLAIM_TTL_SECONDS
            )
        except platform_providers.StateBackendUnavailableError as err:
            logger.warning(
                "Could not claim the identity-provider token refresh; refreshing anyway",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
            return True

    def release(self, user_id: int, idp_id: int) -> None:
        """Release a link's refresh claim, so the next refresh need not wait for it to expire.

        Args:
            user_id: The link's user.
            idp_id: The link's provider.
        """
        try:
            self._state.delete(_CLAIM_KEY.format(user_id=user_id, idp_id=idp_id))
        except platform_providers.StateBackendUnavailableError as err:
            logger.warning(
                "Could not release the identity-provider token refresh claim; it expires on its own",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, idp_id=idp_id),
            )
