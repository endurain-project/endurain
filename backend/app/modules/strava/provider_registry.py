"""Registers Strava as an activity provider ingestion can pull from.

The direction that keeps activities extractable: Strava depends on activities,
never the reverse. Ingestion's refresh path asks the registry what is available
instead of importing this module.
"""

from datetime import datetime

from sqlalchemy.orm import Session

import modules.activities.activity.schema as activities_schema
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.strava.activity_utils as strava_activity_utils

PROVIDER_NAME = "strava"


async def _fetch_window(
    user_id: int,
    window_start: datetime,
    window_end: datetime,
    db: Session,
) -> list[activities_schema.Activity] | None:
    """
    Fetch and store a user's Strava activities recorded in the given window.

    Args:
        user_id: The user whose Strava account to pull from.
        window_start: Inclusive start of the window.
        window_end: Inclusive end of the window.
        db: Database session.

    Returns:
        The stored activities, or ``None`` when Strava is not linked.

    Raises:
        None.
    """
    return await strava_activity_utils.get_user_strava_activities_by_dates(
        start_date=window_start,
        end_date=window_end,
        user_id=user_id,
        db=db,
    )


def register_activity_provider() -> None:
    """
    Register Strava on the activities provider registry.

    Args:
        None.

    Returns:
        None.

    Raises:
        None.
    """
    provider_registry.register(provider_registry.ActivityProvider(PROVIDER_NAME, _fetch_window))
