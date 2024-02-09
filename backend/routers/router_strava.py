import logging
import requests
import os

from datetime import datetime, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from crud import crud_user_integrations, crud_gear, crud_activities
from processors import strava_processor
from dependencies import (
    dependencies_database,
    dependencies_session,
)

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/strava/link",
    tags=["strava"],
)
async def strava_link(
    state: str,
    code: str,
    db: Session = Depends(dependencies_database.get_db),
):
    # Define the token URL
    token_url = "https://www.strava.com/oauth/token"

    # Define the payload
    payload = {
        "client_id": os.environ.get("STRAVA_CLIENT_ID"),
        "client_secret": os.environ.get("STRAVA_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        # Send a POST request to the token URL
        response = requests.post(token_url, data=payload)

        # Check if the response status code is not 200
        if response.status_code != 200:
            # Raise an HTTPException with a 424 Failed Dependency status code
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail="Unable to retrieve tokens from Strava",
            )

        # Get the tokens from the response
        tokens = response.json()

        # Get the user integrations by the state
        user_integrations = (
            crud_user_integrations.get_user_integrations_by_strava_state(state, db)
        )

        # Check if user integrations is None
        if user_integrations is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User integrations not found",
            )

        # Update the user integrations with the tokens
        crud_user_integrations.link_strava_account(user_integrations, tokens, db)

        # Redirect to the main page or any other desired page after processing
        redirect_url = (
            "https://"
            + os.environ.get("FRONTEND_HOST")
            + "/settings/settings.php?integrationsSettings=1&stravaLinked=1"
        )

        # Return a RedirectResponse to the redirect URL
        return RedirectResponse(url=redirect_url)
    except Exception as err:
        # Log the exception
        logger.error(f"Error in strava_link: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.get(
    "/strava/activities/days/{days}",
    status_code=202,
    tags=["strava"],
)
async def strava_retrieve_activities_days(
    days: int,
    user_id: Annotated[
        int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)
    ],
    #db: Annotated[Session, Depends(dependencies_database.get_db)],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        strava_processor.get_user_strava_activities_by_days,
        (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S"),
        user_id,
    )

    # Return success message and status code 202
    logger.info(f"Strava activities will be processed in the background for user {user_id}")
    return {
        "detail": f"Strava activities will be processed in the background for for {user_id}"
    }


@router.put(
    "/strava/set-user-unique-state/{state}",
    tags=["strava"],
)
async def strava_set_user_unique_state(
    state: str,
    user_id: Annotated[
        int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)
    ],
    db: Annotated[Session, Depends(dependencies_database.get_db)],
):
    # Set the user Strava state
    crud_user_integrations.set_user_strava_state(user_id, state, db)

    # Return success message
    return {"detail": f"Strava state for user {user_id} edited successfully"}


@router.put(
    "/strava/unset-user-unique-state",
    tags=["strava"],
)
async def strava_unset_user_unique_state(
    user_id: Annotated[
        int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)
    ],
    db: Annotated[Session, Depends(dependencies_database.get_db)],
):
    # Set the user Strava state
    crud_user_integrations.set_user_strava_state(user_id, None, db)

    # Return success message
    return {"detail": f"Strava state for user {user_id} removed successfully"}


@router.delete("/strava/unlink", tags=["strava"])
async def strava_unlink(
    token_user_id: Annotated[
        int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # delete all strava gear for user
    crud_gear.delete_all_strava_gear_for_user(token_user_id, db)

    # delete all strava activities for user
    crud_activities.delete_all_strava_activities_for_user(token_user_id, db)

    # unlink strava account
    crud_user_integrations.unlink_strava_account(token_user_id, db)

    # Return success message
    return {"detail": f"Strava unlinked for user {token_user_id} successfully"}