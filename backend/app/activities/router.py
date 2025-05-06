import os
import glob
import calendar

from typing import Annotated, Callable

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    Security,
    BackgroundTasks,
)
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

import activities.schema as activities_schema
import activities.utils as activities_utils
import activities.crud as activities_crud
import activities.dependencies as activities_dependencies

import session.security as session_security

import gears.dependencies as gears_dependencies

import garmin.activity_utils as garmin_activity_utils

import users.dependencies as users_dependencies

import strava.activity_utils as strava_activity_utils

import core.logger as core_logger

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "/user/{user_id}/week/{week_number}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_user_activities_week(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    week_number: int,
    validate_week_number: Annotated[
        Callable, Depends(activities_dependencies.validate_week_number)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
    # Calculate the start of the requested week
    today = datetime.now(timezone.utc)
    start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
    end_of_week = start_of_week + timedelta(days=6)

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
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
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
    # Calculate the start of the current week
    today = datetime.now(timezone.utc)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
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
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
    # Calculate the start of the current month
    today = datetime.now(timezone.utc)
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )

    if user_id == token_user_id:
        # Get all user activities for the requested month if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )
    else:
        # Get user following activities for the requested month if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )

    # Return the activities distances for this month
    return activities_utils.calculate_activity_distances(activities)


@router.get(
    "/user/{user_id}/thismonth/number",
    response_model=int,
)
async def read_activities_user_activities_this_month_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(session_security.get_user_id_from_access_token),
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
            user_id, start_of_month, end_of_month, db
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
    "/user/gear/{gear_id}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_gear_activities(
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(session_security.get_user_id_from_access_token),
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
    "/user/{user_id}/number",
    response_model=int,
)
async def read_activities_user_activities_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the number of activities for the user
    activities = activities_crud.get_user_activities(user_id, db)

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/user/{user_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_user_activities_pagination(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activities for the user with pagination
    activities = activities_crud.get_user_activities_with_pagination(
        user_id, db, page_number, num_records
    )

    # Check if activities is None and return None if it is
    if activities is None:
        return None

    # Return activities
    return activities


@router.get(
    "/user/{user_id}/followed/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_followed_user_activities_pagination(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
    # Set the activities to empty list
    activities = []

    # Get the strava activities for the user for the last 24h
    strava_activities = strava_activity_utils.get_user_strava_activities_by_days(
        (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        token_user_id,
        db,
    )

    # Get the garmin activities for the user for the last 24h
    garmin_activities = garmin_activity_utils.get_user_garminconnect_activities_by_days(
        (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
        token_user_id,
        db,
    )

    # Extend the activities to the list
    if strava_activities is not None:
        activities.extend(strava_activities)
    
    if garmin_activities is not None:
        activities.extend(garmin_activities)

    # Check if activities is None and return None if it is
    if activities is None:
        return None

    # Return the activities
    return activities


@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity | None,
)
async def read_activities_activity_from_id(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
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
        Depends(session_security.get_user_id_from_access_token),
    ],
    file: UploadFile,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    try:
        # Return activity/activities
        return activities_utils.parse_and_store_activity_from_uploaded_file(
            token_user_id, file, db
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
        Depends(session_security.get_user_id_from_access_token),
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    background_tasks: BackgroundTasks,
):
    try:
        # Ensure the 'bulk_import' directory exists
        bulk_import_dir = "files/bulk_import"
        os.makedirs(bulk_import_dir, exist_ok=True)

        # Iterate over each file in the 'bulk_import' directory
        for filename in os.listdir(bulk_import_dir):
            file_path = os.path.join(bulk_import_dir, filename)

            if os.path.isfile(file_path):
                # Log the file being processed
                core_logger.print_to_log_and_console(f"Processing file: {file_path}")
                # Parse and store the activity
                background_tasks.add_task(
                    activities_utils.parse_and_store_activity_from_file,
                    token_user_id,
                    file_path,
                    db,
                )

        # Return a success message
        return {"Bulk import initiated. Processing files in the background."}
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
        Depends(session_security.get_user_id_from_access_token),
    ],
    activity_attributes: activities_schema.ActivityEdit,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:write"])
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
async def edit_activity(
    visibility: int,
    validate_visibility: Annotated[
        Callable, Depends(activities_dependencies.validate_visibility)
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:write"])
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
    validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:write"])
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
    pattern = f"files/processed/{activity_id}.*"

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
