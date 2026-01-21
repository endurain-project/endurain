import calendar
import glob
import os
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import activities.activity.crud as activities_crud
import activities.activity.dependencies as activities_dependencies
import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils
import core.database as core_database
import core.dependencies as core_dependencies
import core.logger as core_logger
import core.config as core_config
import gears.gear.dependencies as gears_dependencies
import auth.security as auth_security
import users.users.dependencies as users_dependencies
import garmin.activity_utils as garmin_activity_utils
import strava.activity_utils as strava_activity_utils
import websocket.manager as websocket_manager
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Security,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

# Define the API router
router = APIRouter()

# Define the thread pool executor with 2 workers
executor = ThreadPoolExecutor(max_workers=2)


@router.get(
    "/user/{user_id}/week/{week_number}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_user_activities_week(
    user_id: int,
    _validate_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_user_id)
    ],
    week_number: int,
    _validate_week_number: Annotated[
        Callable, Depends(activities_dependencies.validate_week_number)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
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
    # Calculate the start of the requested week
    today = datetime.now(timezone.utc)
    start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
    end_of_week = start_of_week + timedelta(days=6)

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db, True
        )
    else:
        # Get user following activities for the requested week if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )

    # Check if activities is None
    if activities is None:
        # Return None if activities is None
        return None

    # Return the activities
    return activities


@router.get(
    "/user/{user_id}/thisweek/distances",
    response_model=activities_schema.ActivityDistances | None,
)
async def read_activities_user_activities_this_week_distances(
    user_id: int,
    _validate_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_user_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
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
    # Calculate the start of the current week
    today = datetime.now(timezone.utc)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db, True
        )
    else:
        # Get user following activities for the requested week if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )

    # Return the activities distances for this week
    return activities_utils.calculate_activity_distances(activities)


@router.get(
    "/user/{user_id}/thismonth/distances",
    response_model=activities_schema.ActivityDistances | None,
)
async def read_activities_user_activities_this_month_distances(
    user_id: int,
    _validate_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_user_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
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
    # Calculate the start of the current month
    today = datetime.now(timezone.utc)
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )

    if user_id == token_user_id:
        # Get all user activities for the requested month if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db, True
        )
    else:
        # Get user following activities for the requested month if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )

    # if activities is None:
    # Return None if activities is None
    #    return None

    # Return the activities distances for this month
    return activities_utils.calculate_activity_distances(activities)


@router.get(
    "/user/{user_id}/thismonth/number",
    response_model=int,
)
async def read_activities_user_activities_this_month_number(
    user_id: int,
    _validate_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_user_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Calculate the start of the current month
    today = datetime.now(timezone.utc)
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )

    if user_id == token_user_id:
        # Get all user activities for the requested month if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db, True
        )
    else:
        # Get user following activities for the requested month if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/gear/{gear_id}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_gear_activities(
    gear_id: int,
    _validate_gear_id: Annotated[
        Callable, Depends(gears_dependencies.validate_gear_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activities for the gear
    return activities_crud.get_user_activities_by_gear_id_and_user_id(
        token_user_id, gear_id, db
    )


@router.get(
    "/gear/{gear_id}/number",
    response_model=int,
)
async def read_activities_gear_activities_number(
    gear_id: int,
    _validate_gear_id: Annotated[
        Callable, Depends(gears_dependencies.validate_gear_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the number of activities for the gear
    activities = activities_crud.get_user_activities_by_gear_id_and_user_id(
        token_user_id, gear_id, db
    )
    if activities is None:
        return 0
    return len(activities)


@router.get(
    "/gear/{gear_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_gear_activities_with_pagination(
    gear_id: int,
    _validate_gear_id: Annotated[
        Callable, Depends(gears_dependencies.validate_gear_id)
    ],
    page_number: int,
    num_records: int,
    _validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activities for the gear with pagination
    return activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
        token_user_id, gear_id, page_number, num_records, db
    )


@router.get(
    "/number",
    response_model=int,
)
async def read_activities_user_activities_number(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    # Added dependencies for optional query parameters
    _validate_activity_type: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_type)
    ],
    # Added optional filter query parameters
    activity_type: int | None = Query(None, alias="type"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    name_search: str | None = Query(None),
):
    # Get the number of activities for the user
    activities = activities_crud.get_user_activities(
        user_id=token_user_id,
        db=db,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
    )

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/types",
    response_model=dict | None,
)
async def read_activities_types(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
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
    return activities_crud.get_distinct_activity_types_for_user(token_user_id, db)


@router.get(
    "/user/{user_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_user_activities_pagination(
    user_id: int,
    _validate_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_user_id)
    ],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    # Added dependencies for optional query parameters
    _validate_activity_type: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_type)
    ],
    _validate_sort_by: Annotated[
        Callable, Depends(activities_dependencies.validate_sort_by)
    ],
    _validate_sort_order: Annotated[
        Callable, Depends(activities_dependencies.validate_sort_order)
    ],
    # Added optional filter query parameters
    activity_type: int | None = Query(None, alias="type"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    name_search: str | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str | None = Query(None),
):
    user_is_owner = True
    if token_user_id != user_id:
        user_is_owner = False
    # Get and return the activities for the user with pagination and filters
    return activities_crud.get_user_activities_with_pagination(
        user_id=user_id,
        db=db,
        page_number=page_number,
        num_records=num_records,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
        user_is_owner=user_is_owner,
    )


@router.get(
    "/user/{user_id}/followed/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity]
    | None,  # Keep old response model for now
)
async def read_activities_followed_user_activities_pagination(
    user_id: int,
    _validate_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_user_id)
    ],
    page_number: int,
    num_records: int,
    _validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activities for the following users with pagination
    return activities_crud.get_user_following_activities_with_pagination(
        user_id, page_number, num_records, db
    )


@router.get(
    "/user/{user_id}/followed/number",
    response_model=int,
)
async def read_activities_followed_user_activities_number(
    user_id: int,
    _validate_user_id: Annotated[
        Callable, Depends(users_dependencies.validate_user_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the number of activities for the following users
    activities = activities_crud.get_user_following_activities(user_id, db)

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/refresh",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_user_activities_refresh(
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    # Set the activities to empty list
    activities = []

    # Get the strava activities for the user for the last 24h
    strava_activities = await strava_activity_utils.get_user_strava_activities_by_dates(
        start_date=datetime.now(timezone.utc) - timedelta(days=1),
        end_date=datetime.now(timezone.utc),
        user_id=token_user_id,
        ws_manager=ws_manager,
        db=db,
    )

    # Get the garmin activities for the user for the last 24h
    garmin_activities = (
        await garmin_activity_utils.get_user_garminconnect_activities_by_dates(
            start_date=datetime.now(timezone.utc) - timedelta(days=1),
            end_date=datetime.now(timezone.utc),
            user_id=token_user_id,
            ws_manager=ws_manager,
            db=db,
        )
    )

    # Extend the activities to the list
    if strava_activities is not None:
        activities.extend(strava_activities)

    if garmin_activities is not None:
        activities.extend(garmin_activities)

    # Filter out None values from the activities list
    activities = [activity for activity in activities if activity is not None]

    # Return the activities or None if the list is empty
    return activities if activities else None


@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity | None,
)
async def read_activities_activity_from_id(
    activity_id: int,
    _validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
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
    # Get the activity from the database and return it
    return activities_crud.get_activity_by_id_from_user_id_or_has_visibility(
        activity_id, token_user_id, db
    )


@router.get(
    "/name/contains/{name}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_contain_name(
    name: str,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
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
    # Get the activities from the database by name
    return activities_crud.get_activities_if_contains_name(name, token_user_id, db)


@router.post(
    "/create/upload",
    status_code=201,
    response_model=list[activities_schema.Activity],
)
async def create_activity_with_uploaded_file(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    file: UploadFile,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:write"])
    ],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Return activity/activities
        return await activities_utils.parse_and_store_activity_from_uploaded_file(
            token_user_id, file, ws_manager, db
        )
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_with_uploaded_file: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise err


@router.post(
    "/create/bulkimport",
)
async def create_activity_with_bulk_import(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:write"])
    ],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    try:
        core_logger.print_to_log_and_console("Bulk import initiated.")

        # Ensure the 'bulk_import' directory exists
        bulk_import_dir = core_config.FILES_BULK_IMPORT_DIR
        os.makedirs(bulk_import_dir, exist_ok=True)

        # Grab list of supported file formats
        supported_file_formats = core_config.SUPPORTED_FILE_FORMATS

        # Iterate over each file in the 'bulk_import' directory
        files_to_process = []
        for filename in os.listdir(bulk_import_dir):
            file_path = os.path.join(bulk_import_dir, filename)

            # Check if file is one we can process
            _, file_extension = os.path.splitext(file_path)
            if file_extension not in supported_file_formats:
                core_logger.print_to_log_and_console(
                    f"Skipping file {file_path} due to not having a supported file extension. Supported extensions are: {supported_file_formats}."
                )
                # Might be good to notify the user, but background tasks cannot raise HTTPExceptions
                continue

            if os.path.isfile(file_path):
                files_to_process.append(file_path)
                # Log the file being processed
                core_logger.print_to_log_and_console(
                    f"Queuing file for processing: {file_path}"
                )

        # Submit ONE task that processes all files
        loop = asyncio.get_event_loop()
        loop.run_in_executor(
            executor,
            partial(
                activities_utils.process_all_files_sync,
                token_user_id,
                files_to_process,
                ws_manager,
            ),
        )

        # Log a success message that explains processing will continue elsewhere.
        core_logger.print_to_log_and_console(
            "Bulk import initiated for all files found in the bulk_import directory. Processing of files will continue in the background."
        )

        # Return a success message
        return {
            "Bulk import initiated for all files found in the bulk_import directory. Processing of files will continue in the background."
        }
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_with_bulk_import: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.put(
    "/edit",
)
async def edit_activity(
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    activity_attributes: activities_schema.ActivityEdit,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the activity in the database
    activities_crud.edit_activity(token_user_id, activity_attributes, db)

    # Return success message
    return {f"Activity ID {activity_attributes.id} updated successfully"}


@router.put(
    "/visibility/{visibility}",
)
async def edit_activity_visibility(
    visibility: int,
    _validate_visibility: Annotated[
        Callable, Depends(activities_dependencies.validate_visibility)
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the activities in the database
    activities_crud.edit_user_activities_visibility(token_user_id, visibility, db)

    # Return success message
    return {f"Visibility change to {visibility} for all user activities"}


@router.delete(
    "/{activity_id}/delete",
)
async def delete_activity(
    activity_id: int,
    _validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:write"])
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
    # Get the activity by id from user id
    activity = activities_crud.get_activity_by_id_from_user_id(
        activity_id, token_user_id, db
    )

    # Check if activity is None and raise an HTTPException with a 404 Not Found status code if it is
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity ID {activity_id} for user {token_user_id} not found",
        )

    # Delete the activity
    activities_crud.delete_activity(activity_id, db)

    # Define the search pattern using the file ID (e.g., '1.*')
    pattern = f"{core_config.FILES_PROCESSED_DIR}/{activity_id}.*"

    # Use glob to find files that match the pattern
    files_to_delete = glob.glob(pattern)

    # Delete each matching file
    for file in files_to_delete:
        try:
            os.remove(file)
        except FileNotFoundError as err:
            # Log the exception
            core_logger.print_to_log(f"File not found {file}: {err}", "error", exc=err)
        except Exception as err:
            # Log the exception
            core_logger.print_to_log(
                f"Error deleting file {file}: {err}", "error", exc=err
            )

    # Return success message
    return {"detail": f"Activity {activity_id} deleted successfully"}
