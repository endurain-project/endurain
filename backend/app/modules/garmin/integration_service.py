"""The operation other modules may call on Garmin Connect: registering it as an activity provider.

The direction that keeps activities extractable: Garmin depends on activities,
never the reverse. Ingestion's refresh path asks the registry what is available
instead of importing this module.
"""

from datetime import datetime

import modules.activities.activity.schema as activity_schema
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.garmin.activity_service as garmin_activity_service
import modules.garmin.constants as garmin_constants
import modules.users.users_integrations.integration_service as user_integrations_integration
from core.database import SessionLocal


def _fetch_window(
    user_id: int,
    window_start: datetime,
    window_end: datetime,
) -> list[activity_schema.ActivityRead] | None:
    """Fetch and store a user's Garmin Connect activities recorded in the given window.

    Args:
        user_id: The user whose Garmin Connect account to pull from.
        window_start: Inclusive start of the window.
        window_end: Inclusive end of the window.

    Returns:
        The stored activities, or ``None`` when Garmin Connect is not linked.
    """
    return garmin_activity_service.get_user_garminconnect_activities_by_dates(window_start, window_end, user_id)


def _linked_user_ids(after_id: int, limit: int) -> list[int]:
    """Page through the users who have linked Garmin Connect.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.

    Returns:
        The linked user ids, ascending.
    """
    with SessionLocal() as db:
        return user_integrations_integration.list_user_ids_with_garminconnect_linked(after_id, limit, db)


def register_activity_provider() -> None:
    """Register Garmin Connect on the activities provider registry."""
    activity_ingestion_integration.register_activity_provider(
        garmin_constants.PROVIDER_NAME, _fetch_window, _linked_user_ids
    )
