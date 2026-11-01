"""Shared record of an external provider's rate limit, kept in the platform state provider.

A provider that answers 429 has to be left alone by every process and replica until the limit clears,
so the flag lives in the shared state rather than in process memory. Each flag's value is the instant
it expires, which lets a sync that stops on it defer exactly that long. The flags are TTL keys, so
they expire on their own.

What a flag is *for* (an application, a user) and how long a limit lasts is the provider's: the store
only keeps and reads the flags.
"""

from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers

import core.logger as core_logger

logger = core_logger.get_logger(__name__)

#: How long a flag whose recorded expiry cannot be read is taken to last, so a sync that waits never
#: waits for less than a limit lasts.
UNREADABLE_EXPIRY_SECONDS = 15 * 60


class ProviderRateLimitStore:
    """Rate-limit flags of one provider over a platform ``StateProvider``.

    Every method fails open when the shared state is unreachable: a missed back-off costs one
    rejected call, which records the limit again, whereas failing closed would stop every call for
    as long as the state store is down.

    Attributes:
        _state: The platform state provider.
        _provider: The provider that owns the flags, in the storage keys.
    """

    def __init__(self, state: platform_providers.StateProvider, provider: str) -> None:
        """Bind the store to a state provider.

        Args:
            state: The platform state provider.
            provider: The provider that owns the flags, in the storage keys.
        """
        self._state = state
        self._provider = provider

    def _key(self, subject: str) -> str:
        return f"{self._provider}:rate_limited:{subject}"

    def mark(self, subject: str, expires_at: datetime) -> None:
        """Record that a subject is rate limited until an instant.

        Args:
            subject: What the provider limited: an application, a user.
            expires_at: When the limit clears.
        """
        ttl = max(1, int((expires_at - datetime.now(UTC)).total_seconds()))
        try:
            self._state.set(self._key(subject), expires_at.isoformat().encode(), ttl_seconds=ttl)
        except platform_providers.StateBackendUnavailableError as err:
            logger.error(
                "Could not record a provider rate limit",
                exc_info=err,
                extra=core_logger.context(provider=self._provider),
            )

    def expiry(self, subject: str) -> datetime | None:
        """Return when a subject's rate limit clears.

        Args:
            subject: What the provider limited.

        Returns:
            When the limit clears, or ``None`` when none is active or the state is unreachable.
        """
        try:
            value = self._state.get(self._key(subject))
        except platform_providers.StateBackendUnavailableError as err:
            logger.warning(
                "Could not read a provider rate limit; assuming none",
                exc_info=err,
                extra=core_logger.context(provider=self._provider),
            )
            return None
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.decode())
        except ValueError:
            return datetime.now(UTC) + timedelta(seconds=UNREADABLE_EXPIRY_SECONDS)
