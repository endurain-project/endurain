"""Durable-job subscribers for the Strava module.

The gear sync and unlink routes answer 202 and hand the work here, because both are chains of
Strava round trips and deletes that do not belong on a request thread. The channel is
durable-delivery only: without ``JOBS_ENABLED`` the routes run the same body on an in-process pool.
"""

import jasil.runtime as platform_runtime
from jasil.jobs.registry import JobHandlerRegistry

import core.sync_runner as core_sync_runner
import modules.strava.events as strava_events
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.sync_service as strava_sync_service
import modules.strava.sync_state_store as strava_sync_state_store

SYNC_REQUESTED_SUBSCRIBER_ID = "strava.sync_requested"


def _run_sync(payload: strava_events.SyncRequestedPayload, will_retry: bool) -> None:
    """Run one queued gear sync or unlink over the platform state.

    Args:
        payload: What to run.
        will_retry: Whether a durable worker runs it again if it raises.
    """
    state = platform_runtime.get_state()
    strava_sync_service.run_sync(
        payload,
        strava_sync_state_store.StravaSyncStateStore(state),
        strava_rate_limit_store.StravaRateLimitStore(state),
        will_retry=will_retry,
    )


def _close_sync(payload: strava_events.SyncRequestedPayload) -> None:
    """Close a gear sync or unlink the runner gave up on.

    Args:
        payload: What was to run.
    """
    strava_sync_service.close_dead_lettered_sync(
        payload, strava_sync_state_store.StravaSyncStateStore(platform_runtime.get_state())
    )


def register_durable_handlers(registry: JobHandlerRegistry) -> None:
    """Register the Strava sync as a durable job, with the dead-letter hook that closes it.

    Args:
        registry: The durable-subscriber registry to register on.
    """
    core_sync_runner.register_sync_job(
        registry,
        strava_events.STRAVA_SYNC_REQUESTED,
        SYNC_REQUESTED_SUBSCRIBER_ID,
        strava_events.SyncRequestedPayload,
        run=_run_sync,
        close=_close_sync,
    )
