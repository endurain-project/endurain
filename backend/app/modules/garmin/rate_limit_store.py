"""Garmin Connect's shared rate-limit state: a per-user flag over the platform ``StateProvider``.

Garmin Connect throttles an account, not an application, and reports no reset time, so a limit is
recorded for one cooldown. Every process and replica reads the same flag, so a sync that was refused
is not repeated by another replica's scheduled pull. See :class:`core.provider_rate_limit.ProviderRateLimitStore`.
"""

from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers

import core.provider_rate_limit as core_provider_rate_limit
import modules.garmin.constants as garmin_constants


class GarminRateLimitStore:
    """Garmin Connect rate-limit flags, keyed by user.

    Attributes:
        _limits: The shared flag storage.
    """

    def __init__(self, state: platform_providers.StateProvider) -> None:
        """Bind the store to a state provider.

        Args:
            state: The platform state provider.
        """
        self._limits = core_provider_rate_limit.ProviderRateLimitStore(state, garmin_constants.PROVIDER_NAME)

    def mark_rate_limited(self, user_id: int) -> datetime:
        """Record that Garmin Connect rate limited a user's account, for one cooldown.

        Args:
            user_id: The user whose account was limited.

        Returns:
            When the limit is taken to clear.
        """
        expires_at = datetime.now(UTC) + timedelta(seconds=garmin_constants.RATE_LIMIT_COOLDOWN_SECONDS)
        self._limits.mark(str(user_id), expires_at)
        return expires_at

    def rate_limited_until(self, user_id: int) -> datetime | None:
        """Return when a user's active rate limit clears.

        Fails open when the shared state is unreachable.

        Args:
            user_id: The user about to be synced.

        Returns:
            When the limit clears, or ``None`` when none is active or the state is unreachable.
        """
        return self._limits.expiry(str(user_id))
