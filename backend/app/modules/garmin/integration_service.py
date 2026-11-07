"""The operation other modules may call on Garmin Connect: registering it as an activity provider.

The direction that keeps activities extractable: Garmin depends on activities,
never the reverse. Ingestion's refresh path asks the registry what is available
instead of importing this module.
"""

from datetime import datetime

import jasil.runtime as platform_runtime

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.activity_service as garmin_activity_service
import modules.garmin.constants as garmin_constants
import modules.garmin.link_service as garmin_link_service
import modules.garmin.rate_limit_store as garmin_rate_limit_store
import modules.garmin.service as garmin_service
import modules.garmin.sync_service as garmin_sync_service


def _fetch_window(
    user_id: int, window_start: datetime, window_end: datetime
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store a user's Garmin Connect activities recorded in the given window.

    Args:
        user_id: The user whose Garmin Connect account to pull from.
        window_start: Inclusive start of the window.
        window_end: Inclusive end of the window.

    Returns:
        The stored activities, or ``None`` when Garmin Connect is not linked or nothing new came back.
    """
    return garmin_activity_service.get_user_garminconnect_activities_by_dates(
        user_id,
        window_start,
        window_end,
        garmin_rate_limit_store.GarminRateLimitStore(platform_runtime.get_state()),
    )


def register_activity_provider() -> None:
    """Register Garmin Connect on the activities provider registry."""
    activity_ingestion_integration.register_activity_provider(
        garmin_constants.PROVIDER_NAME, _fetch_window, garmin_service.linked_user_ids
    )


def shutdown_pools() -> None:
    """Stop the Garmin Connect link and sync pools."""
    garmin_link_service.shutdown_link_pool()
    garmin_sync_service.shutdown_sync_pool()
