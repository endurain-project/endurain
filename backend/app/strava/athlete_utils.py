from fastapi import HTTPException, status
from stravalib.client import Client

def get_strava_athlete(strava_client: Client):
    # Fetch Strava athlete
    strava_athlete = strava_client.get_athlete()

    if strava_athlete is None:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail="Not able to fetch Strava athlete",
        )
    
    return strava_athlete