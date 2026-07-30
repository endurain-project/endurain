"""Entry point for a provider refresh initiated through the API.

The provider-coupled sibling of :mod:`upload_entry` and :mod:`bulk_entry`: it
owns the Strava/Garmin specifics so :mod:`ingestion_jobs`, which both job kinds
share, stays provider-agnostic (enforced by the ``ingestion-pipeline-provider-
agnostic`` import-linter contract).

Still ``async`` because the provider helpers are: they wrap blocking HTTP
clients in ``asyncio.to_thread``. The caller drives this with ``asyncio.run`` on
a worker thread, so none of it touches the main event loop.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.activities.activity.schema as activities_schema
import modules.garmin.activity_utils as garmin_activity_utils
import modules.strava.activity_utils as strava_activity_utils
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)

# How far back a refresh looks. Matches the previous route's behaviour.
_REFRESH_WINDOW = timedelta(days=1)


async def sync_linked_providers(user_id: int, db: Session) -> list[activities_schema.Activity]:
    """Fetch the recent window of activities from every linked provider.

    A provider that is not linked returns nothing rather than failing, so one
    unlinked integration does not fail the whole refresh.

    Args:
        user_id: The user whose providers to sync.
        db: Database session.

    Returns:
        The activities the providers produced, in provider order.
    """
    window_end = datetime.now(UTC)
    window_start = window_end - _REFRESH_WINDOW

    strava_activities = await strava_activity_utils.get_user_strava_activities_by_dates(
        start_date=window_start,
        end_date=window_end,
        user_id=user_id,
        db=db,
    )
    garmin_activities = await garmin_activity_utils.get_user_garminconnect_activities_by_dates(
        start_date=window_start,
        end_date=window_end,
        user_id=user_id,
        # The process-local manager, not a request dependency: this runs on a
        # worker with no request. Frames are handed to the main loop by the
        # notification helper, which is what keeps them on the loop that owns
        # the websocket connections.
        ws_manager=websocket_manager.get_websocket_manager(),
        db=db,
    )

    activities = [*(strava_activities or []), *(garmin_activities or [])]
    return [activity for activity in activities if activity is not None]
