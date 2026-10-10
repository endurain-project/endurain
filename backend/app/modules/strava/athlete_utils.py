from fastapi import HTTPException, status
from stravalib.client import Client

import core.logger as core_logger

logger = core_logger.get_logger(__name__)


def get_strava_athlete(strava_client: Client):
    # Fetch Strava athlete
    try:
        strava_athlete = strava_client.get_athlete()
    except Exception as err:
        logger.error(f"Error fetching Strava athlete: {err}. Returning 424 Failed Dependency", exc_info=err)
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Error fetching Strava athlete",
        ) from err

    if strava_athlete is None:
        logger.error("Not able to fetch Strava athlete. Returning 424 Failed Dependency")
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava athlete",
        )

    return strava_athlete
