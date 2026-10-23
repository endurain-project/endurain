"""Durable-job subscribers for the Garmin Connect module.

The gear and health sync routes answer 202 and hand the work here, because a sync is a chain of
Garmin round trips that does not belong on a request thread. The channel is durable-delivery
only: without ``JOBS_ENABLED`` the routes run the same body on an in-process pool.
"""

import jasil.event_versioning as platform_event_versioning
import jasil.runtime as platform_runtime
from jasil.events import Event
from jasil.jobs.registry import JobHandlerRegistry

import core.logger as core_logger
import modules.garmin.events as garmin_events
import modules.garmin.sync_service as garmin_sync_service
import modules.garmin.sync_state_store as garmin_sync_state_store

logger = core_logger.get_logger(__name__)

SYNC_REQUESTED_SUBSCRIBER_ID = "garmin.sync_requested"


def process_sync_requested_for_event(event: Event) -> None:
    """Durable handler: run one queued gear or health sync.

    Args:
        event: The ``garmin.sync_requested`` event.
    """
    payload = platform_event_versioning.parse_payload(garmin_events.SyncRequestedPayload, event)
    garmin_sync_service.run_sync(payload, garmin_sync_state_store.GarminSyncStateStore(platform_runtime.get_state()))
    logger.debug(
        "Garmin Connect sync job finished",
        extra=core_logger.context(user_id=payload.user_id, kind=payload.kind),
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the Garmin Connect sync handler as a durable job subscriber.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    registry.register(
        garmin_events.GARMIN_SYNC_REQUESTED,
        SYNC_REQUESTED_SUBSCRIBER_ID,
        process_sync_requested_for_event,
    )
