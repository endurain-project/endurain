"""Entry point for a provider refresh: pull recent activities from linked providers.

Fans a refresh out across the providers registered on
:mod:`~modules.activities.activity_ingestion.provider_registry`. It names no
provider: doing so is what made activities and Strava/Garmin mutually dependent,
since both providers import back into the ingestion seam.

Synchronous and session-less. The caller is a job body on a worker thread, the
provider adapters wrap blocking HTTP clients, and each provider opens a short
session per unit of work, so no database transaction is held across a provider
round trip.
"""

from datetime import UTC, datetime, timedelta

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.provider_registry as activity_ingestion_provider_registry

logger = core_logger.get_logger(__name__)

# How far back a refresh looks when the job names no window.
_REFRESH_WINDOW = timedelta(days=1)


def sync_linked_providers(
    user_id: int,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    *,
    provider: str | None = None,
) -> list[activity_schema.ActivityRead]:
    """Fetch a window of activities from the user's linked providers.

    A provider the user has not linked returns nothing rather than failing, so
    one unlinked integration does not fail the whole refresh. A provider that
    raises is logged and the remaining providers still run, but the sync then
    fails, so the durable runner retries it with backoff (or the job is recorded
    as failed when nothing retries).

    Args:
        user_id: The user whose providers to sync.
        window_start: Start of the window; defaults to a day before ``window_end``.
        window_end: End of the window; defaults to now.
        provider: Sync only this provider; ``None`` syncs every registered one.

    Returns:
        The activities the providers produced, in registration order.

    Raises:
        ProcessingError: When a named provider is not registered in this process
            (a worker that lacks a registration the API has would otherwise
            complete the job having synced nothing), or when any provider's
            fetch raised.
    """
    end = window_end or datetime.now(UTC)
    start = window_start or end - _REFRESH_WINDOW

    providers: tuple[activity_ingestion_provider_registry.ActivityProvider, ...]
    if provider is not None:
        selected = activity_ingestion_provider_registry.get(provider)
        if selected is None:
            logger.error(
                "Refresh asked for a provider that is not registered in this process",
                extra=core_logger.context(user_id=user_id, provider=provider),
            )
            raise core_exceptions.ProcessingError()
        providers = (selected,)
    else:
        providers = activity_ingestion_provider_registry.registered()
        if not providers:
            logger.debug(
                "Refresh requested with no providers registered",
                extra=core_logger.context(user_id=user_id),
            )

    activities: list[activity_schema.ActivityRead] = []
    first_failure: Exception | None = None
    for candidate in providers:
        try:
            produced = candidate.fetch_window(user_id, start, end)
        except Exception as err:
            logger.error(
                "Provider refresh failed; continuing with the remaining providers",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, provider=candidate.name),
            )
            first_failure = first_failure or err
            continue
        activities.extend(activity for activity in (produced or []) if activity is not None)

    if first_failure is not None:
        # Raised only after every provider was tried, so one outage does not starve
        # the others; the retry re-reads the window, and ingestion dedup makes
        # that a no-op for what already arrived.
        raise core_exceptions.ProcessingError() from first_failure

    return activities
