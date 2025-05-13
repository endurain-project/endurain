from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client

import core.logger as core_logger

import strava.utils as strava_utils

def get_strava_athlete(strava_client: Client):
    # Fetch Strava athlete
    try:
        strava_athlete = strava_client.get_athlete()
    except Exception as err:
        core_logger.print_to_log(
            f"Error fetching Strava athlete: {err}. Returning 424 Failed Dependency",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Error fetching Strava athlete",
        )

    if strava_athlete is None:
        core_logger.print_to_log(
            "Not able to fetch Strava athlete. Returning 424 Failed Dependency", "error"
        )
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava athlete",
        )

    return strava_athlete
