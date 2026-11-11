"""The operation other modules may call on Strava: registering it as an activity provider.

The direction that keeps activities extractable: Strava depends on activities,
never the reverse. Ingestion's refresh path asks the registry what is available
instead of importing this module.
"""

from datetime import datetime

import jasil.runtime as platform_runtime
from jasil.providers import StateProvider

import core.job_status as core_job_status
import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.strava.activity_service as strava_activity_service
import modules.strava.bulk_import_service as strava_bulk_import_service
import modules.strava.constants as strava_constants
import modules.strava.link_service as strava_link_service
import modules.strava.rate_limit_store as strava_rate_limit_store
import modules.strava.schema as strava_schema
import modules.strava.service as strava_service
import modules.strava.sync_service as strava_sync_service
import modules.strava.sync_state_store as strava_sync_state_store


def _fetch_window(
    user_id: int,
    window_start: datetime,
    window_end: datetime,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store a user's Strava activities recorded in the given window.

    Args:
        user_id: The user whose Strava account to pull from.
        window_start: Inclusive start of the window.
        window_end: Inclusive end of the window.

    Returns:
        The stored activities, or ``None`` when Strava is not linked.
    """
    return strava_activity_service.get_user_strava_activities_by_dates(
        user_id,
        window_start,
        window_end,
        strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state()),
    )


def register_activity_provider() -> None:
    """Register Strava, and its export format, on the activities provider registry."""
    activity_ingestion_integration.register_activity_provider(
        strava_constants.PROVIDER_NAME, _fetch_window, strava_service.linked_user_ids
    )
    strava_bulk_import_service.register_bulk_import_format()


def shutdown_pools() -> None:
    """Stop the Strava link and sync pools."""
    strava_link_service.shutdown_link_pool()
    strava_sync_service.shutdown_sync_pool()


def read_sync_job(job: core_job_status.JobRef, state: StateProvider) -> strava_schema.StravaSyncStatus | None:
    """Read a Strava link, gear sync or unlink by its job reference.

    Args:
        job: The job's reference.
        state: The platform state provider.

    Returns:
        The job's status, or None when it expired or a later sync of the same kind replaced it.
    """
    found = strava_sync_state_store.StravaSyncStateStore(state).read_job(job)
    if found is None:
        return None
    current, sync_state = found
    return strava_schema.StravaSyncStatus.model_validate({**current.envelope(), "status": sync_state.status})
