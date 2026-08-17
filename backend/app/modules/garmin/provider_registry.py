"""Registers Garmin Connect as an activity provider ingestion can pull from.

The direction that keeps activities extractable: Garmin depends on activities,
never the reverse. Ingestion's refresh path asks the registry what is available
instead of importing this module.
"""

from datetime import datetime

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.garmin.activity_utils as garmin_activity_utils
import modules.websocket.manager as websocket_manager

PROVIDER_NAME = "garminconnect"


async def _fetch_window(
    user_id: int,
    window_start: datetime,
    window_end: datetime,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """
    Fetch and store a user's Garmin Connect activities recorded in the given window.

    Args:
        user_id: The user whose Garmin Connect account to pull from.
        window_start: Inclusive start of the window.
        window_end: Inclusive end of the window.
        db: Database session.

    Returns:
        The stored activities, or ``None`` when Garmin Connect is not linked.

    Raises:
        None.
    """
    return await garmin_activity_utils.get_user_garminconnect_activities_by_dates(
        start_date=window_start,
        end_date=window_end,
        user_id=user_id,
        # The process-local manager, not a request dependency: a refresh runs on
        # a worker with no request. Frames are handed to the main loop by the
        # notification helper, which is what keeps them on the loop that owns
        # the websocket connections.
        ws_manager=websocket_manager.get_websocket_manager(),
        db=db,
    )


def register_activity_provider() -> None:
    """
    Register Garmin Connect on the activities provider registry.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    provider_registry.register(provider_registry.ActivityProvider(PROVIDER_NAME, _fetch_window))
