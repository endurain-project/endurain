from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from stravalib.client import Client
import time

import core.cryptography as core_cryptography
import core.logger as core_logger

import activities.activity.schema as activities_schema
import activities.activity.crud as activities_crud

import users.user_integrations.crud as user_integrations_crud
import users.user_integrations.models as user_integrations_models

import users.user.crud as users_crud

from core.database import SessionLocal


def refresh_strava_tokens(is_startup: bool = False):
    # Create a new database session using context manager
    with SessionLocal() as db:
        # Get all users
        users = users_crud.get_all_users(db)

        # Iterate through all users
        if users:
            for user in users:
                refresh_user_strava_token(user.id, db, is_startup)


def refresh_user_strava_token(user_id: int, db: Session, is_startup: bool = False):
    # Get the user integrations by user ID
    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user_id, db
    )

    # Check if user_integrations strava token is not None
    if (
        user_integrations.strava_token is not None
        and user_integrations.strava_refresh_token is not None
        and user_integrations.strava_token_expires_at is not None
        and user_integrations.strava_client_id is not None
        and user_integrations.strava_client_secret is not None
    ):
        refresh_time = user_integrations.strava_token_expires_at.replace(
            tzinfo=timezone.utc
        ) - timedelta(minutes=60)

        if datetime.now(timezone.utc) > refresh_time:
            try:
                strava_client = create_strava_client(user_integrations)
                tokens = strava_client.refresh_access_token(
                    client_id=core_cryptography.decrypt_token_fernet(
                        user_integrations.strava_client_id
                    ),
                    client_secret=core_cryptography.decrypt_token_fernet(
                        user_integrations.strava_client_secret
                    ),
                    refresh_token=core_cryptography.decrypt_token_fernet(
                        user_integrations.strava_refresh_token
                    ),
                )

                # Update the user integrations with the tokens
                user_integrations_crud.link_strava_account(
                    user_integrations, tokens, db
                )

                core_logger.print_to_log(f"User {user_id}: Strava tokens refreshed")
            except Exception as err:
                # Log the exception
                core_logger.print_to_log(
                    f"Error in refresh_strava_token: {err}", "error"
                )

                # Raise an HTTPException with a 500 Internal Server Error status code
                if not is_startup:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Internal Server Error",
                    ) from err
    else:
        # Log an informational event if the user does not have a Strava token
        core_logger.print_to_log(
            f"User {user_id}: No Strava token found. Will skip processing"
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
        core_logger.print_to_log(
            f"User {user_id}: Activity {activity_id} already exists. Will skip processing"
        )

        # Return None
        return activity_db
    else:
        return None


def fetch_user_integrations_and_validate_token(
    user_id: int, db: Session
) -> user_integrations_models.UsersIntegrations | None:
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
    user_integrations: user_integrations_models.UsersIntegrations,
) -> Client:
    # Convert to epoch timestamp
    epoch_time = (
        int(time.mktime(user_integrations.strava_token_expires_at.timetuple()))
        if user_integrations.strava_token_expires_at
        else None
    )

    # Create a Strava client with the user's access token and return it
    try:
        return Client(
            access_token=(
                core_cryptography.decrypt_token_fernet(user_integrations.strava_token)
                if user_integrations.strava_token
                else None
            ),
            refresh_token=(
                core_cryptography.decrypt_token_fernet(
                    user_integrations.strava_refresh_token
                )
                if user_integrations.strava_refresh_token
                else None
            ),
            token_expires=epoch_time,
        )
    except Exception as err:
        # Log the error and re-raise the exception
        core_logger.print_to_log_and_console(
            f"Error in create_strava_client: {err}", "error", err
        )
        raise err
