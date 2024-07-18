import os
import logging
import calendar

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, Security
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

import activities.schema as activities_schema
import activities.utils as activies_utils
import activities.crud as activities_crud
import activities.dependencies as activities_dependencies

import session.security as session_security

import gears.crud as gears_crud
import gears.dependencies as gears_dependencies

import users.dependencies as users_dependencies

import activity_streams.crud as activity_streams_crud

import gpx.utils as gpx_utils

import fit.utils as fit_utils

import database
import dependencies_global

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/user/{user_id}/week/{week_number}",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_useractivities_week(
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
        Depends(database.get_db),
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
async def read_activities_useractivities_thisweek_distances(
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
        Depends(database.get_db),
    ],
):
    # Calculate the start of the current week
    today = datetime.now(timezone.utc)
    start_of_week = today - timedelta(
        days=today.weekday()
    )
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
    #if activities is None:
        # Return None if activities is None
    #    return None

    # Return the activities distances for this week
    return activies_utils.calculate_activity_distances(activities)


@router.get(
    "/user/{user_id}/thismonth/distances",
    response_model=activities_schema.ActivityDistances | None,
)
async def read_activities_useractivities_thismonth_distances(
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
        Depends(database.get_db),
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

    #if activities is None:
        # Return None if activities is None
    #    return None

    # Return the activities distances for this month
    return activies_utils.calculate_activity_distances(activities)


@router.get(
    "/user/{user_id}/thismonth/number",
    response_model=int,
)
async def read_activities_useractivities_thismonth_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(
            session_security.get_user_id_from_access_token
        ),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
async def read_activities_gearactivities(
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        Callable,
        Depends(
            session_security.get_user_id_from_access_token
        ),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
async def read_activities_useractivities_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
async def read_activities_useractivities_pagination(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(dependencies_global.validate_pagination_values)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
        Callable, Depends(dependencies_global.validate_pagination_values)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
async def read_activities_followed_useractivities_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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
        Depends(database.get_db),
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
        Depends(database.get_db),
    ],
):
    # Get the activities from the database by name
    return activities_crud.get_activities_if_contains_name(name, token_user_id, db)


@router.post(
    "/create/upload",
    status_code=201,
    response_model=activities_schema.Activity,
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
        Depends(database.get_db),
    ],
):
    try:
        # Ensure the 'uploads' directory exists
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)

        # Get file extension
        _, file_extension = os.path.splitext(file.filename)

        # Save the uploaded file in the 'uploads' directory
        with open(file.filename, "wb") as save_file:
            save_file.write(file.file.read())

        # Choose the appropriate parser based on file extension
        if file_extension.lower() == ".gpx":
            # Parse the GPX file
            parsed_info = gpx_utils.parse_gpx_file(file.filename, token_user_id)
        elif file_extension.lower() == ".fit":
            # Parse the FIT file
            parsed_info = fit_utils.parse_fit_file(file.filename, token_user_id)
        else:
            # file extension not supported raise an HTTPException with a 406 Not Acceptable status code
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail="File extension not supported. Supported file extensions are .gpx and .fit",
            )

        # create the activity in the database
        created_activity = activities_crud.create_activity(parsed_info["activity"], db)

        # Check if created_activity is None
        if created_activity is None:
            # raise an HTTPException with a 500 Internal Server Error status code
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creating activity",
            )

        # Parse the activity streams from the parsed info
        activity_streams = gpx_utils.parse_activity_streams_from_gpx_file(
            parsed_info, created_activity.id
        )

        # Create activity streams in the database
        activity_streams_crud.create_activity_streams(activity_streams, db)

        # Remove the file after processing
        os.remove(file.filename)

        # Return activity ID
        return created_activity
    except Exception as err:
        # Log the exception
        logger.error(
            f"Error in create_activity_with_uploaded_file: {err}", exc_info=True
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
        Depends(database.get_db),
    ],
):
    # Update the activity in the database
    activities_crud.edit_activity(token_user_id, activity_attributes, db)

    # Return success message
    return {f"Activity ID {activity_attributes.id} updated successfully"}


@router.put(
    "/{activity_id}/addgear/{gear_id}",
)
async def activity_add_gear(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:write"])
    ],
    token_user_id: Annotated[
        int,
        Depends(
            session_security.get_user_id_from_access_token
        ),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the gear by user id and gear id
    gear = gears_crud.get_gear_user_by_id(token_user_id, gear_id, db)

    # Check if gear is None and raise an HTTPException with a 404 Not Found status code if it is
    if gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear ID {gear_id} for user {token_user_id} not found",
        )

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

    # Add the gear to the activity
    activities_crud.add_gear_to_activity(activity_id, gear_id, db)

    # Return success message
    return {"detail": f"Gear ID {gear_id} added to activity successfully"}


@router.put(
    "/{activity_id}/deletegear",
)
async def delete_activity_gear(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_id)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:write"])
    ],
    token_user_id: Annotated[
        int,
        Depends(
            session_security.get_user_id_from_access_token
        ),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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

    # Delete gear from the activity
    activities_crud.add_gear_to_activity(activity_id, None, db)

    # Return success message
    return {"detail": f"Gear ID {activity.gear_id} deleted from activity successfully"}


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
        Depends(
            session_security.get_user_id_from_access_token
        ),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
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

    # Return success message
    return {"detail": f"Activity {activity_id} deleted successfully"}
