"""Durable-job subscribers for the Strava module.

The gear sync and unlink routes answer 202 and hand the work here, because both are chains of
Strava round trips and deletes that do not belong on a request thread. The channel is
durable-delivery only: without ``JOBS_ENABLED`` the routes run the same body on an in-process pool.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.logger as core_logger
import modules.strava.events as strava_events
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.sync_service as strava_sync_service
import modules.strava.sync_state_store as strava_sync_state_store

logger = core_logger.get_logger(__name__)

SYNC_REQUESTED_SUBSCRIBER_ID = "strava.sync_requested"


def process_sync_requested_for_event(event: Event) -> None:
    """Durable handler: run one queued gear sync or unlink.

    Args:
        event: The ``strava.sync_requested`` event.
    """
    payload = platform_event_versioning.parse_payload(strava_events.SyncRequestedPayload, event)
    state = platform_runtime.get_state()
    strava_sync_service.run_sync(
        payload,
        strava_sync_state_store.StravaSyncStateStore(state),
        strava_rate_limit_store.StravaRateLimitStore(state),
        will_retry=not event.is_last_attempt,
    )
    logger.debug("Strava sync job finished", extra=core_logger.context(user_id=payload.user_id, kind=payload.kind))


def on_sync_requested_dead_letter(event: Event, error: str | None) -> None:
    """Close a sync the runner gave up on.

    Args:
        event: The ``strava.sync_requested`` event.
        error: What the runner recorded, which the sync's own log line already carries.
    """
    payload = platform_event_versioning.parse_payload(strava_events.SyncRequestedPayload, event)
    strava_sync_service.close_dead_lettered_sync(
        payload, strava_sync_state_store.StravaSyncStateStore(platform_runtime.get_state())
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the Strava sync handler as a durable job subscriber.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        strava_events.STRAVA_SYNC_REQUESTED,
        SYNC_REQUESTED_SUBSCRIBER_ID,
        process_sync_requested_for_event,
        on_dead_letter=on_sync_requested_dead_letter,
    )
