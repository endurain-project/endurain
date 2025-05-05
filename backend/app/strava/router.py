import requests

from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Security
from sqlalchemy.orm import Session

import session.security as session_security

import user_integrations.crud as user_integrations_crud

import gears.crud as gears_crud

import activities.crud as activities_crud

import strava.gear_utils as strava_gear_utils
import strava.activity_utils as strava_activity_utils
import strava.utils as strava_utils
import strava.schema as strava_schema

import core.logger as core_logger
import core.database as core_database

# Define the API router
router = APIRouter()


@router.put(
    "/link",
)
async def strava_link(
    state: str,
    code: str,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the user integrations by the state
    user_integrations = (
        user_integrations_crud.get_user_integrations_by_strava_state(state, db)
    )

    # Check if user integrations is None
    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User integrations not found",
        )
    
    if user_integrations.strava_client_id is None or user_integrations.strava_client_secret is None:
        # Set the user Strava client to None
        user_integrations_crud.set_user_strava_client(
            user_integrations.user_id, None, None, db
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava client ID or secret not set",
        )
    
    # Define the token URL
    token_url = "https://www.strava.com/oauth/token"

    # Define the payload
    payload = {
        "client_id": user_integrations.strava_client_id,
        "client_secret": user_integrations.strava_client_secret,
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

        # Update the user integrations with the tokens
        user_integrations_crud.link_strava_account(user_integrations, tokens, db)
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in strava_link: {err}", "error", exc=err)
        
        # Set the user Strava client to None
        user_integrations_crud.set_user_strava_client(
            user_integrations.user_id, None, None, db
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.get(
    "/activities/days/{days}",
    status_code=202,
)
async def strava_retrieve_activities_days(
    days: int,
    validate_access_token: Annotated[
        Callable,
        Depends(session_security.validate_access_token),
    ],
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    # db: Annotated[Session, Depends(core_database.get_db)],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        strava_activity_utils.get_user_strava_activities_by_days,
        (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        token_user_id,
    )

    # Return success message and status code 202
    core_logger.print_to_log(
        f"Strava activities will be processed in the background for user {token_user_id}"
    )
    return {
        "detail": f"Strava activities will be processed in the background for for {token_user_id}"
    }


@router.get("/gear", status_code=202)
async def strava_retrieve_gear(
    validate_access_token: Annotated[
        Callable,
        Depends(session_security.validate_access_token),
    ],
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        strava_gear_utils.get_user_gear,
        token_user_id,
    )

    # Return success message and status code 202
    core_logger.print_to_log(
        f"Strava gear will be processed in the background for user {token_user_id}"
    )
    return {
        "detail": f"Strava gear will be processed in the background for for {token_user_id}"
    }


@router.put(
    "/client"
)
async def strava_set_user_client(
    client: strava_schema.StravaClient,
    validate_access_token: Annotated[
        Callable,
        Depends(session_security.validate_access_token),
    ],
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Set the user Strava client
    user_integrations_crud.set_user_strava_client(
        token_user_id, client.client_id, client.client_secret, db
    )

    # Return success message
    return {f"Strava client for user {token_user_id} edited successfully"}


@router.put(
    "/state/{state}",
)
async def strava_set_user_unique_state(
    state: str | None,
    validate_access_token: Annotated[
        Callable,
        Depends(session_security.validate_access_token),
    ],
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Set the user Strava state
    user_integrations_crud.set_user_strava_state(token_user_id, state, db)

    # Return success message
    return {f"Strava state for user {token_user_id} edited successfully"}


@router.delete("/unlink")
async def strava_unlink(
    validate_access_token: Annotated[
        Callable,
        Depends(session_security.validate_access_token),
    ],
    check_scopes: Annotated[
        Callable,
        Security(session_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get Strava client
    strava_client = strava_utils.create_strava_client(
        strava_utils.fetch_user_integrations_and_validate_token(token_user_id, db)
    )

    # Deauthorize the Strava client
    if strava_client:
        strava_client.deauthorize()

    # delete all strava gear for user
    gears_crud.delete_all_strava_gear_for_user(token_user_id, db)

    # delete all strava activities for user
    activities_crud.delete_all_strava_activities_for_user(token_user_id, db)

    # unlink strava account
    user_integrations_crud.unlink_strava_account(token_user_id, db)

    # Return success message
    return {"detail": f"Strava unlinked for user {token_user_id} successfully"}
