import time
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client

import core.logger as core_logger

import activities.schema as activities_schema
import activities.crud as activities_crud

import user_integrations.schema as user_integrations_schema
import user_integrations.crud as user_integrations_crud


def fetch_and_validate_activity(
    activity_id: int, user_id: int, db: Session
) -> activities_schema.Activity | None:
    # Get the activity by Strava ID from the user
    activity_db = activities_crud.get_activity_by_strava_id_from_user_id(
        activity_id, user_id, db
    )

    # Check if activity is None
    if activity_db:
        # Log an informational event if the activity already exists
        core_logger.print_to_log(
            f"User {user_id}: Activity {activity_id} already exists. Will skip processing"
        )

        # Return None
        return activity_db
    else:
        return None


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UsersIntegrations | None:
    # Get the user integrations by user ID
    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user_id, db
    )

    # Check if user integrations is None
    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User information not found",
        )

    # Check if user_integrations.strava_token_expires_at is None
    if user_integrations.strava_token_expires_at is None:
        return None

    # Return the user integrations
    return user_integrations


def create_strava_client(
    user_integrations: user_integrations_schema.UsersIntegrations,
) -> Client:
    # Convert to epoch timestamp
    epoch_time = int(time.mktime(user_integrations.strava_token_expires_at.timetuple()))

    # Create a Strava client with the user's access token and return it
    return Client(
        access_token=user_integrations.strava_token,
        refresh_token=user_integrations.strava_refresh_token,
        token_expires=epoch_time,
    )
