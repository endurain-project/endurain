import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from functools import partial
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Security, status
from sqlalchemy.orm import Session
from stravalib.exc import AccessUnauthorized

import core.config as core_config
import core.cryptography as core_cryptography
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.integration_service as activities_integration
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.crud as gears_crud
import modules.strava.activity_utils as strava_activity_utils
import modules.strava.bulk_import_utils as strava_bulk_import_utils
import modules.strava.gear_utils as strava_gear_utils
import modules.strava.schema as strava_schema
import modules.strava.utils as strava_utils
import modules.users.users_integrations.crud as user_integrations_crud
import modules.websocket.manager as websocket_manager

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()

# Define the thread pool executor with 2 workers
executor = ThreadPoolExecutor(max_workers=2)


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
    user_integrations = user_integrations_crud.get_user_integrations_by_strava_state(state, db)

    # Check if user integrations is None
    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User integrations not found",
        )

    # Check if client ID and client secret are set
    if user_integrations.strava_client_id is None and user_integrations.strava_client_secret is None:
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
        user_integrations_crud.link_strava_account(user_integrations.user_id, tokens, db)

        # Return success message
        return {"detail": f"Strava linked successfully for user {user_integrations.user_id}"}
    except Exception as err:
        logger.error(f"Unable to link Strava account: {err}", exc_info=err)

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
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    # db: Annotated[Session, Depends(core_database.get_db)],
    background_tasks: BackgroundTasks,
):
    start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
    end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)

    # Process strava activities in the background
    background_tasks.add_task(
        strava_activity_utils.get_user_strava_activities_by_dates,
        start_datetime,
        end_datetime,
        token_user_id,
    )

    # Return success message and status code 202
    logger.info(f"Strava activities will be processed in the background for user {token_user_id}")
    return {"detail": f"Strava activities will be processed in the background for for {token_user_id}"}


@router.get("/gear", status_code=201)
async def strava_retrieve_gear(
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        strava_gear_utils.get_user_gear,
        token_user_id,
    )

    # Return success message and status code 202
    logger.info(f"Strava gear will be processed in the background for user {token_user_id}")
    return {"detail": f"Strava gear will be processed in the background for for {token_user_id}"}


@router.post("/import/bikes", status_code=201)
async def import_bikes_from_strava_export(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Log beginning of bike import
        logger.info("Entering bike importing function")

        # Get bikes from Strava export CSV file
        bikes_dict = strava_gear_utils.iterate_over_bikes_csv()

        # Transform bikes dict to list of Gear schema objects
        if bikes_dict:
            bikes = strava_gear_utils.transform_csv_bike_gear_to_schema_gear(bikes_dict, token_user_id)

            # Add bikes to the database
            if bikes:
                gears_crud.create_multiple_gears(bikes, token_user_id, db)

        # Define variables for moving the bikes file
        processed_dir = core_config.FILES_PROCESSED_DIR
        bulk_import_dir = core_config.STRAVA_BULK_IMPORT_DIR
        bikes_file_name = core_config.STRAVA_BULK_IMPORT_BIKES_FILE
        bikes_file_path = os.path.join(bulk_import_dir, bikes_file_name)

        # Move the bikes file to the processed directory
        core_file_uploads.move_within(bikes_file_path, processed_dir, filename=bikes_file_name)
        logger.info(f"{bikes_file_name} moved to: {processed_dir}.", extra=core_logger.context(console=True))

        # Log completion of bike import
        logger.info("Bike import complete.", extra=core_logger.context(console=True))
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        logger.error(f"Error in import_bikes_from_strava_export: {err}", extra=core_logger.context(console=True))
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.post("/import/shoes", status_code=201)
async def import_shoes_from_strava_export(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Log beginning of shoe import
        logger.info("Entering shoe importing function")

        # Get shoes from Strava export CSV file
        shoes_list = strava_gear_utils.iterate_over_shoes_csv()

        logger.debug("Shoe list created.", extra=core_logger.context(console=True))

        # Transform shoes list to list of Gear schema objects
        if shoes_list:
            shoes = strava_gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, token_user_id, db)

            logger.debug("Shoe list converted to schema gear.", extra=core_logger.context(console=True))

            # Add shoes to the database
            if shoes:
                gears_crud.create_multiple_gears(shoes, token_user_id, db)

        logger.debug("Shoes added to db.", extra=core_logger.context(console=True))

        # Define variables for moving the shoes file
        processed_dir = core_config.FILES_PROCESSED_DIR
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
        shoes_file_name = core_config.STRAVA_BULK_IMPORT_SHOES_FILE
        shoes_file_path = os.path.join(bulk_import_dir, shoes_file_name)

        # Move the shoes file to the processed directory and log it.
        core_file_uploads.move_within(shoes_file_path, processed_dir, filename=shoes_file_name)
        logger.info(f"{shoes_file_name} moved to: {processed_dir}.", extra=core_logger.context(console=True))

        # Log completion of shoe import
        logger.info("Shoe import complete.", extra=core_logger.context(console=True))
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        logger.error(f"Error in import_shoes_from_strava_export: {err}", extra=core_logger.context(console=True))
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.post("/import/activities", status_code=201)
async def import_activities_and_media_from_strava_export(
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    try:
        # Get time of import initiation to pass to function for recording in import_data dictionary, ensuring all activities imported via this bulk import action share an identical import time.
        import_time = datetime.now(UTC).isoformat()
        logger.info(f"Strava bulk import: Initiated at {import_time}.", extra=core_logger.context(console=True))

        # Parse activities data from activities.csv into a dictionary
        strava_activities_dict = strava_bulk_import_utils.iterate_over_activities_csv()

        if strava_activities_dict is None:
            logger.error(
                "ABORTING IMPORT: Aborting strava bulk import due to improperly parsed CSV.",
                extra=core_logger.context(console=True),
            )
            return {"Strava import ABORTED due to lack of, or improperly parsed, activities.csv file."}

        # Create gear list here, so it does not have to be done separately for every single activity that is imported (AND because Strava has a wacked format for shoe naming in their export)
        users_existing_gear_nickname_to_id = strava_bulk_import_utils.create_gear_dictionary_for_bulk_import(
            token_user_id, db
        )

        # Queue files for processing.
        if users_existing_gear_nickname_to_id:
            loop = asyncio.get_event_loop()
            loop.run_in_executor(
                executor,
                partial(
                    strava_bulk_import_utils.queue_bulk_export_activities_for_import,
                    token_user_id,
                    ws_manager,
                    db,
                    strava_activities_dict,
                    users_existing_gear_nickname_to_id,
                    import_time,
                ),
            )

            # Log a success message that explains processing will continue elsewhere.
            logger.info(
                "Strava bulk import initiated. Processing of files will continue in the background.",
                extra=core_logger.context(console=True),
            )
        else:
            logger.error(
                "ABORTING IMPORT: Aborting strava bulk import due to failure in creating gear nickname to id dictionary.",
                extra=core_logger.context(console=True),
            )

        # Return a success message
        return {"Strava bulk import initiated. Processing of files will continue in the background."}
    except Exception as err:
        # Log the exception
        logger.error(f"Error in strava_bulk_import: {err}", extra=core_logger.context(console=True))
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
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Set the user Strava client
    user_integrations_crud.set_user_strava_client(token_user_id, client.client_id, client.client_secret, db)

    # Return success message
    return {f"Strava client for user {token_user_id} edited successfully"}


@router.put(
    "/state/{state}",
)
async def strava_set_user_unique_state(
    state: str | None,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
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
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
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
            logger.info(
                "Unable to deauthorize Strava account, using stravalib deauthorize logic. Will unlink forcibly",
                exc_info=err,
            )

    # delete all strava gear for user
    gears_crud.delete_all_strava_gear_for_user(token_user_id, db)

    # delete all strava activities for user
    activities_integration.delete_all_strava_activities(token_user_id, db)

    # unlink strava account
    user_integrations_crud.unlink_strava_account(token_user_id, db)

    # Return success message
    return {"detail": f"Strava unlinked for user {token_user_id} successfully"}
