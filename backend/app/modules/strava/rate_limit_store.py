"""Strava API rate-limit state, kept in the platform's shared state."""

from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

#: Short-term limits reset every 15 minutes.
SHORT_TERM_COOLDOWN_SECONDS = 15 * 60

_SHORT_TERM_KEY = "strava:rate_limited:short:{client_id}"
_LONG_TERM_KEY = "strava:rate_limited:long:{client_id}"


class StravaRateLimitStore:
    """Tracks Strava API rate limit state over a platform ``StateProvider``.

    The limits are Strava's, per application, so every process and replica has to
    see the same answer: a process-local flag would let each worker keep
    hammering an API another one was already told to back off from. Every user
    brings their own Strava application, so the flags are keyed by client ID: one
    application hitting its limit must not pause the others. The flags are TTL keys
    in the state provider (in-process under the ``local`` profile, Redis when
    distributed), so they expire on their own.
    """

    def __init__(self, state: platform_providers.StateProvider) -> None:
        """Bind the store to a state provider.

        Args:
            state: The platform state provider.
        """
        self._state = state

    def mark_rate_limited(self, client_id: str, is_long_term: bool = False) -> None:
        """Record that a rate limit was hit.

        Args:
            client_id: The Strava application (client ID) that hit the limit.
            is_long_term: True for the daily limit (resets at UTC midnight),
                False for the 15-minute limit.
        """
        now = datetime.now(UTC)
        if is_long_term:
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            key, ttl = _LONG_TERM_KEY.format(client_id=client_id), max(1, int((tomorrow - now).total_seconds()))
            logger.warning(
                "Strava daily rate limit hit, skipping until it resets",
                extra=core_logger.context(client_id=client_id, resets_at=tomorrow),
            )
        else:
            key, ttl = _SHORT_TERM_KEY.format(client_id=client_id), SHORT_TERM_COOLDOWN_SECONDS
            logger.warning(
                "Strava 15-minute rate limit hit, skipping for the cooldown",
                extra=core_logger.context(client_id=client_id, cooldown_seconds=ttl),
            )
        try:
            self._state.set(key, b"1", ttl_seconds=ttl)
        except platform_providers.StateBackendUnavailableError as err:
            logger.error("Could not record the Strava rate limit", exc_info=err)

    def is_rate_limited(self, client_id: str) -> bool:
        """Check if Strava API calls should be skipped for an application.

        Fails open when the shared state is unreachable: a missed back-off costs
        one rejected call, which marks the limit again, whereas failing closed
        would stop every sync for as long as the state store is down.

        Args:
            client_id: The Strava application (client ID) about to be called.

        Returns:
            True if currently rate-limited.
        """
        try:
            return (
                self._state.get(_LONG_TERM_KEY.format(client_id=client_id)) is not None
                or self._state.get(_SHORT_TERM_KEY.format(client_id=client_id)) is not None
            )
        except platform_providers.StateBackendUnavailableError as err:
            logger.warning("Could not read the Strava rate limit state; assuming not limited", exc_info=err)
            return False
