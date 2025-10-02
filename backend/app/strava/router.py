from datetime import datetime, timedelta, timezone
from typing import Annotated, Callable
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Security
from sqlalchemy.orm import Session

from stravalib.exc import AccessUnauthorized

import session.security as session_security

import users.user_integrations.crud as user_integrations_crud

import gears.gear.crud as gears_crud

import activities.activity.crud as activities_crud

import strava.gear_utils as strava_gear_utils
import strava.activity_utils as strava_activity_utils
import strava.utils as strava_utils
import strava.schema as strava_schema

import core.cryptography as core_cryptography
import core.logger as core_logger
import core.database as core_database

import websocket.schema as websocket_schema

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
    user_integrations = user_integrations_crud.get_user_integrations_by_strava_state(
        state, db
    )

    # Check if user integrations is None
    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User integrations not found",
        )

    # Check if client ID and client secret are set
    if (
        user_integrations.strava_client_id is None
        and user_integrations.strava_client_secret is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava client ID and secret not set",
        )

    try:
        # Create a Strava client
        strava_client = strava_utils.create_strava_client(user_integrations)

        # Exchange code for token
        tokens = strava_client.exchange_code_for_token(
            client_id=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id),
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            code=code,
        )

        # Update the user integrations with the tokens
        user_integrations_crud.link_strava_account(user_integrations, tokens, db)

        # Return success message
        return {
            "detail": f"Strava linked successfully for user {user_integrations.user_id}"
        }
    except Exception as err:
        core_logger.print_to_log(
            f"Unable to link Strava account: {err}", "error", exc=err
        )

        # Clean up by setting Strava
        user_integrations_crud.unlink_strava_account(
            user_integrations.user_id, db
        )

        # Raise an HTTPException with appropriate status code
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=f"Unable to link Strava account: {err}",
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
    websocket_manager: Annotated[
        websocket_schema.WebSocketManager,
        Depends(websocket_schema.get_websocket_manager),
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
        websocket_manager,
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


@router.put("/client")
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
        try:
            strava_client.deauthorize()
        except (AccessUnauthorized, Exception) as err:
            core_logger.print_to_log(
                f"Unable to deauthorize Strava account, using stravalib deauthorize logic. Will unlink forcibly",
                "info",
                exc=err,
            )

    # delete all strava gear for user
    gears_crud.delete_all_strava_gear_for_user(token_user_id, db)

    # delete all strava activities for user
    activities_crud.delete_all_strava_activities_for_user(token_user_id, db)

    # unlink strava account
    user_integrations_crud.unlink_strava_account(token_user_id, db)

    # Return success message
    return {"detail": f"Strava unlinked for user {token_user_id} successfully"}
