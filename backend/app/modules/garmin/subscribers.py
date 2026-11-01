"""Durable-job subscribers for the Garmin Connect module.

The gear and health sync routes answer 202 and hand the work here, because a sync is a chain of
Garmin round trips that does not belong on a request thread. The channel is durable-delivery
only: without ``JOBS_ENABLED`` the routes run the same body on an in-process pool.
"""

import jasil.runtime as platform_runtime
from jasil.jobs.registry import JobHandlerRegistry

import core.sync_runner as core_sync_runner
import modules.garmin.events as garmin_events
import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.sync_service as garmin_sync_service
import modules.garmin.sync_state_store as garmin_sync_state_store

SYNC_REQUESTED_SUBSCRIBER_ID = "garmin.sync_requested"


def _run_sync(payload: garmin_events.SyncRequestedPayload, will_retry: bool) -> None:
    """Run one queued gear or health sync over the platform state.

    Args:
        payload: What to run.
        will_retry: Whether a durable worker runs it again if it raises.
    """
    state = platform_runtime.get_state()
    garmin_sync_service.run_sync(
        payload,
        garmin_sync_state_store.GarminSyncStateStore(state),
        garmin_rate_limit_store.GarminRateLimitStore(state),
        will_retry=will_retry,
    )


def _close_sync(payload: garmin_events.SyncRequestedPayload) -> None:
    """Close a gear or health sync the runner gave up on.

    Args:
        payload: What was to run.
    """
    garmin_sync_service.close_dead_lettered_sync(
        payload, garmin_sync_state_store.GarminSyncStateStore(platform_runtime.get_state())
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the Garmin Connect sync as a durable job, with the dead-letter hook that closes it.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    core_sync_runner.register_sync_job(
        registry,
        garmin_events.GARMIN_SYNC_REQUESTED,
        SYNC_REQUESTED_SUBSCRIBER_ID,
        garmin_events.SyncRequestedPayload,
        run=_run_sync,
        close=_close_sync,
    )
