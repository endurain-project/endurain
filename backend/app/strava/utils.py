import os
import requests

from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client

import activities.schema as activities_schema
import activities.crud as activities_crud

import user_integrations.schema as user_integrations_schema
import user_integrations.crud as user_integrations_crud

import users.crud as users_crud

import strava.logger as strava_logger

from core.database import SessionLocal


def refresh_strava_tokens_job():
    # Create a new database session
    db = SessionLocal()
    try:
        # Refresh Strava tokens
        refresh_strava_tokens(db)
    finally:
        # Ensure the session is closed after use
        db.close()


def refresh_strava_tokens(db: Session):
    # Get all users
    users = users_crud.get_all_users(db)

    # Iterate through all users
    for user in users:
        # Get the user integrations by user ID
        user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
            user.id, db
        )

        # Check if user_integrations strava token is not None
        if user_integrations.strava_token is not None:
            # refresh_time = user_integrations.strava_token_expires_at - timedelta(
            #    minutes=60
            # )
            refresh_time = user_integrations.strava_token_expires_at.replace(
                tzinfo=timezone.utc
            ) - timedelta(minutes=60)

            if datetime.now(timezone.utc) > refresh_time:
                # Strava token refresh endpoint
                token_url = "https://www.strava.com/oauth/token"
                # Parameters for the token refresh request
                payload = {
                    "client_id": os.environ.get("STRAVA_CLIENT_ID"),
                    "client_secret": os.environ.get("STRAVA_CLIENT_SECRET"),
                    "refresh_token": user_integrations.strava_refresh_token,
                    "grant_type": "refresh_token",
                }

                try:
                    # Send a POST request to the token URL
                    response = requests.post(token_url, data=payload)

                    # Check if the response status code is not 200
                    if response.status_code != 200:
                        # Raise an HTTPException with a 424 Failed Dependency status code
                        strava_logger.print_to_log(
                            "Unable to retrieve tokens for refresh process from Strava", "error"
                        )

                    tokens = response.json()
                except Exception as err:
                    # Log the exception
                    strava_logger.print_to_log(
                        f"Error in refresh_strava_token: {err}", "error"
                    )

                    # Raise an HTTPException with a 500 Internal Server Error status code
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Internal Server Error",
                    ) from err
                finally:
                    # Update the user integrations with the tokens
                    user_integrations_crud.link_strava_account(
                        user_integrations, tokens, db
                    )

                    strava_logger.print_to_log(
                        f"User {user.id}: Strava tokens refreshed"
                    )


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
        strava_logger.print_to_log(
            f"User {user_id}: Activity {activity_id} already exists. Will skip processing"
        )

        # Return None
        return activity_db
    else:
        return None


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_schema.UserIntegrations | None:
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
    user_integrations: user_integrations_schema.UserIntegrations,
) -> Client:
    # Create a Strava client with the user's access token and return it
    return Client(access_token=user_integrations.strava_token)
