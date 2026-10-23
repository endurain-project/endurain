"""The operation other modules may call on Garmin Connect: registering it as an activity provider.

The direction that keeps activities extractable: Garmin depends on activities,
never the reverse. Ingestion's refresh path asks the registry what is available
instead of importing this module.
"""

import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.activity_service as garmin_activity_service
import modules.garmin.constants as garmin_constants
import modules.garmin.link_service as garmin_link_service
import modules.garmin.service as garmin_service
import modules.garmin.sync_service as garmin_sync_service


def register_activity_provider() -> None:
    """Register Garmin Connect on the activities provider registry."""
    activity_ingestion_integration.register_activity_provider(
        garmin_constants.PROVIDER_NAME,
        garmin_activity_service.get_user_garminconnect_activities_by_dates,
        garmin_service.linked_user_ids,
    )


def shutdown_executors() -> None:
    """Stop the Garmin Connect link and sync threads."""
    garmin_link_service.shutdown_link_executor()
    garmin_sync_service.shutdown_sync_executor()
