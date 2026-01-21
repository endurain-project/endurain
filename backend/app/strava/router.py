import os
from datetime import datetime, timedelta, timezone, date
from typing import Annotated, Callable
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Security
from sqlalchemy.orm import Session

from stravalib.exc import AccessUnauthorized

import auth.security as auth_security

import users.users_integrations.crud as user_integrations_crud

import gears.gear.crud as gears_crud

import activities.activity.crud as activities_crud
import activities.activity.utils as activities_utils

import strava.gear_utils as strava_gear_utils
import strava.activity_utils as strava_activity_utils
import strava.utils as strava_utils
import strava.schema as strava_schema

import core.config as core_config
import core.cryptography as core_cryptography
import core.logger as core_logger
import core.database as core_database

import websocket.manager as websocket_manager

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
            client_id=core_cryptography.decrypt_token_fernet(
                user_integrations.strava_client_id
            ),
            client_secret=core_cryptography.decrypt_token_fernet(
                user_integrations.strava_client_secret
            ),
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
        user_integrations_crud.unlink_strava_account(user_integrations.user_id, db)

        # Raise an HTTPException with appropriate status code
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=f"Unable to link Strava account: {err}",
        ) from err


@router.get(
    "/activities",
    status_code=202,
)
async def strava_retrieve_activities_days(
    start_date: date,
    end_date: date,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_security.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    websocket_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    # db: Annotated[Session, Depends(core_database.get_db)],
    background_tasks: BackgroundTasks,
):
    start_datetime = datetime.combine(
        start_date, datetime.min.time(), tzinfo=timezone.utc
    )
    end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)

    # Process strava activities in the background
    background_tasks.add_task(
        strava_activity_utils.get_user_strava_activities_by_dates,
        start_datetime,
        end_datetime,
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


@router.get("/gear", status_code=201)
async def strava_retrieve_gear(
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_security.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
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


@router.post("/import/bikes", status_code=201)
async def import_bikes_from_strava_export(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Log beginning of bike import
        core_logger.print_to_log("Entering bike importing function")

        # Get bikes from Strava export CSV file
        bikes_dict = strava_gear_utils.iterate_over_bikes_csv()

        # Transform bikes dict to list of Gear schema objects
        if bikes_dict:
            bikes = strava_gear_utils.transform_csv_bike_gear_to_schema_gear(
                bikes_dict, token_user_id
            )

            # Add bikes to the database
            if bikes:
                gears_crud.create_multiple_gears(bikes, token_user_id, db)

        # Define variables for moving the bikes file
        processed_dir = core_config.FILES_PROCESSED_DIR
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
        bikes_file_name = core_config.STRAVA_BULK_IMPORT_BIKES_FILE
        bikes_file_path = os.path.join(bulk_import_dir, bikes_file_name)

        # Move the bikes file to the processed directory
        activities_utils.move_file(processed_dir, bikes_file_name, bikes_file_path)
        core_logger.print_to_log_and_console(
            f"{bikes_file_name} moved to: {processed_dir}."
        )

        # Log completion of bike import
        core_logger.print_to_log_and_console("Bike import complete.")
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(
            f"Error in import_bikes_from_strava_export: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.post("/import/shoes", status_code=201)
async def import_shoes_from_strava_export(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sid_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Log beginning of shoe import
        core_logger.print_to_log("Entering shoe importing function")

        # Get shoes from Strava export CSV file
        shoes_list = strava_gear_utils.iterate_over_shoes_csv()

        # Transform shoes list to list of Gear schema objects
        if shoes_list:
            shoes = strava_gear_utils.transform_csv_shoe_gear_to_schema_gear(
                shoes_list, token_user_id, db
            )

            # Add shoes to the database
            if shoes:
                gears_crud.create_multiple_gears(shoes, token_user_id, db)

        # Define variables for moving the shoes file
        processed_dir = core_config.FILES_PROCESSED_DIR
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
        shoes_file_name = core_config.STRAVA_BULK_IMPORT_SHOES_FILE
        shoes_file_path = os.path.join(bulk_import_dir, shoes_file_name)

        # Move the shoes file to the processed directory and log it.
        activities_utils.move_file(processed_dir, shoes_file_name, shoes_file_path)
        core_logger.print_to_log_and_console(
            f"{shoes_file_name} moved to: {processed_dir}."
        )

        # Log completion of shoe import
        core_logger.print_to_log_and_console("Shoe import complete.")
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log_and_console(
            f"Error in import_shoes_from_strava_export: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.put("/client")
async def strava_set_user_client(
    client: strava_schema.StravaClient,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_security.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
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
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_security.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Set the user Strava state
    user_integrations_crud.set_user_strava_state(token_user_id, state, db)

    # Return success message
    return {f"Strava state for user {token_user_id} edited successfully"}


@router.delete("/unlink")
async def strava_unlink(
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_security.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_security.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
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
