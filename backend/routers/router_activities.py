import os
import logging
import calendar

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from schemas import schema_activities
from crud import crud_activities, crud_activity_streams, crud_gear
from dependencies import (
    dependencies_database,
    dependencies_session,
    dependencies_users,
    dependencies_activities,
    dependencies_gear,
    dependencies_global,
)
from processors import gpx_processor, fit_processor

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/activities/user/{user_id}/week/{week_number}",
    response_model=list[schema_activities.Activity] | None,
    tags=["activities"],
)
async def read_activities_useractivities_week(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    week_number: int,
    validate_week_number: Annotated[
        Callable, Depends(dependencies_activities.validate_week_number)
    ],
    token_user_id: Annotated[
        Callable,
        Depends(dependencies_session.validate_token_and_get_authenticated_user_id),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Calculate the start of the requested week
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
    end_of_week = start_of_week + timedelta(days=7)

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = crud_activities.get_user_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )
    else:
        # Get user following activities for the requested week if the user is not the owner of the token
        activities = crud_activities.get_user_following_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )

    # Check if activities is None
    if activities is None:
        # Return None if activities is None
        return None

    # Return the activities
    return activities


@router.get(
    "/activities/user/{user_id}/thisweek/distances",
    response_model=schema_activities.ActivityDistances | None,
    tags=["activities"],
)
async def read_activities_useractivities_thisweek_distances(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    token_user_id: Annotated[
        Callable,
        Depends(dependencies_session.validate_token_and_get_authenticated_user_id),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Calculate the start of the current week
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(
        days=today.weekday()
    )  # Monday is the first day of the week, which is denoted by 0
    end_of_week = start_of_week + timedelta(days=7)

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = crud_activities.get_user_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )
    else:
        # Get user following activities for the requested week if the user is not the owner of the token
        activities = crud_activities.get_user_following_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )

    # Check if activities is None
    if activities is None:
        # Return None if activities is None
        return None

    # Return the activities distances for this week
    return schema_activities.calculate_activity_distances(activities)


@router.get(
    "/activities/user/{user_id}/thismonth/distances",
    response_model=schema_activities.ActivityDistances | None,
    tags=["activities"],
)
async def read_activities_useractivities_thismonth_distances(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    token_user_id: Annotated[
        Callable,
        Depends(dependencies_session.validate_token_and_get_authenticated_user_id),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Calculate the start of the current month
    today = datetime.utcnow().date()
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )

    if user_id == token_user_id:
        # Get all user activities for the requested month if the user is the owner of the token
        activities = crud_activities.get_user_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )
    else:
        # Get user following activities for the requested month if the user is not the owner of the token
        activities = crud_activities.get_user_following_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )

    if activities is None:
        # Return None if activities is None
        return None

    # Return the activities distances for this month
    return schema_activities.calculate_activity_distances(activities)


@router.get(
    "/activities/user/{user_id}/thismonth/number",
    response_model=int,
    tags=["activities"],
)
async def read_activities_useractivities_thismonth_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    token_user_id: Annotated[
        Callable,
        Depends(dependencies_session.validate_token_and_get_authenticated_user_id),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Calculate the start of the current month
    today = datetime.utcnow().date()
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )

    if user_id == token_user_id:
        # Get all user activities for the requested month if the user is the owner of the token
        activities = crud_activities.get_user_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )
    else:
        # Get user following activities for the requested month if the user is not the owner of the token
        activities = crud_activities.get_user_following_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/activities/user/{user_id}/gear/{gear_id}",
    response_model=list[schema_activities.Activity] | None,
    tags=["activities"],
)
async def read_activities_gearactivities(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(dependencies_gear.validate_gear_id)],
    validate_token_and_if_user_id_equals_token_user_id_if_not_validate_admin_access: Annotated[
        Callable,
        Depends(
            dependencies_session.validate_token_and_if_user_id_equals_token_user_id_if_not_validate_admin_access
        ),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activities for the gear
    return crud_activities.get_user_activities_by_gear_id_and_user_id(user_id, gear_id, db)


@router.get(
    "/activities/user/{user_id}/number",
    response_model=int,
    tags=["activities"],
)
async def read_activities_useractivities_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Annotated[Callable, Depends(dependencies_session.validate_token)],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the number of activities for the user
    activities = crud_activities.get_user_activities(user_id, db)

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/activities/user/{user_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=list[schema_activities.Activity] | None,
    tags=["activities"],
)
async def read_activities_useractivities_pagination(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(dependencies_global.validate_pagination_values)
    ],
    validate_token: Annotated[Callable, Depends(dependencies_session.validate_token)],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activities for the user with pagination
    activities = crud_activities.get_user_activities_with_pagination(
        user_id, db, page_number, num_records
    )

    # Check if activities is None and return None if it is
    if activities is None:
        return None

    # Return activities
    return activities


@router.get(
    "/activities/user/{user_id}/followed/page_number/{page_number}/num_records/{num_records}",
    response_model=list[schema_activities.Activity] | None,
    tags=["activities"],
)
async def read_activities_followed_user_activities_pagination(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(dependencies_global.validate_pagination_values)
    ],
    validate_token: Annotated[Callable, Depends(dependencies_session.validate_token)],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activities for the following users with pagination
    return crud_activities.get_user_following_activities_with_pagination(
        user_id, page_number, num_records, db
    )


@router.get(
    "/activities/user/{user_id}/followed/number",
    response_model=int,
    tags=["activities"],
)
async def read_activities_followed_useractivities_number(
    user_id: int,
    validate_user_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Annotated[Callable, Depends(dependencies_session.validate_token)],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the number of activities for the following users
    activities = crud_activities.get_user_following_activities(user_id, db)

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/activities/{activity_id}",
    response_model=schema_activities.Activity | None,
    tags=["activities"],
)
async def read_activities_activity_from_id(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(dependencies_activities.validate_activity_id)
    ],
    token_user_id: Annotated[
        Callable,
        Depends(dependencies_session.validate_token_and_get_authenticated_user_id),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activity from the database and return it
    return crud_activities.get_activity_by_id_from_user_id_or_has_visibility(activity_id, token_user_id, db)


@router.get(
    "/activities/name/contains/{name}",
    response_model=list[schema_activities.Activity] | None,
    tags=["activities"],
)
async def read_activities_contain_name(
    name: str,
    token_user_id: Annotated[
        Callable,
        Depends(dependencies_session.validate_token_and_get_authenticated_user_id),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activities from the database by name
    return crud_activities.get_activities_if_contains_name(name, token_user_id, db)


@router.post(
    "/activities/create/upload",
    status_code=201,
    response_model=int,
    tags=["activities"],
)
async def create_activity_with_uploaded_file(
    token_user_id: Annotated[
        Callable,
        Depends(dependencies_session.validate_token_and_get_authenticated_user_id),
    ],
    file: UploadFile,
    db: Session = Depends(dependencies_database.get_db),
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
            parsed_info = gpx_processor.parse_gpx_file(file.filename, token_user_id)
        elif file_extension.lower() == ".fit":
            # Parse the FIT file
            parsed_info = fit_processor.parse_fit_file(file.filename, token_user_id)
        else:
            # file extension not supported raise an HTTPException with a 406 Not Acceptable status code
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail="File extension not supported. Supported file extensions are .gpx and .fit",
            )

        # create the activity in the database
        created_activity = crud_activities.create_activity(parsed_info["activity"], db)

        # Check if created_activity is None
        if created_activity is None:
            # raise an HTTPException with a 500 Internal Server Error status code
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error creating activity",
            )

        # Parse the activity streams from the parsed info
        activity_streams = gpx_processor.parse_activity_streams_from_gpx_file(
            parsed_info, created_activity.id
        )

        # Create activity streams in the database
        crud_activity_streams.create_activity_streams(activity_streams, db)

        # Remove the file after processing
        os.remove(file.filename)

        # Return activity ID
        return created_activity.id
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


@router.put("/activities/{activity_id}/addgear/{gear_id}",
    tags=["activities"],
)
async def activity_add_gear(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(dependencies_activities.validate_activity_id)
    ],
    gear_id: int,
    validate_gear_id: Annotated[Callable, Depends(dependencies_gear.validate_gear_id)],
    token_user_id: Annotated[int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the gear by user id and gear id
    gear = crud_gear.get_gear_user_by_id(token_user_id, gear_id, db)

    # Check if gear is None and raise an HTTPException with a 404 Not Found status code if it is
    if gear is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gear ID {gear_id} for user {token_user_id} not found",
        )
    
    # Get the activity by id from user id 
    activity = crud_activities.get_activity_by_id_from_user_id(activity_id, token_user_id, db)

    # Check if activity is None and raise an HTTPException with a 404 Not Found status code if it is
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity ID {activity_id} for user {token_user_id} not found",
        )

    # Add the gear to the activity
    crud_activities.add_gear_to_activity(activity_id, gear_id, db)
    
    # Return success message
    return {"detail": f"Gear ID {gear_id} added to activity successfully"}

@router.put("/activities/{activity_id}/deletegear",
    tags=["activities"],
)
async def delete_activity_gear(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(dependencies_activities.validate_activity_id)
    ],
    token_user_id: Annotated[int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activity by id from user id 
    activity = crud_activities.get_activity_by_id_from_user_id(activity_id, token_user_id, db)

    # Check if activity is None and raise an HTTPException with a 404 Not Found status code if it is
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity ID {activity_id} for user {token_user_id} not found",
        )

    # Delete gear from the activity
    crud_activities.add_gear_to_activity(activity_id, None, db)
    
    # Return success message
    return {"detail": f"Gear ID {activity.gear_id} deleted from activity successfully"}

@router.delete("/activities/{activity_id}/delete",
    tags=["activities"],
)
async def delete_activity(
    activity_id: int,
    validate_activity_id: Annotated[
        Callable, Depends(dependencies_activities.validate_activity_id)
    ],
    token_user_id: Annotated[int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the activity by id from user id 
    activity = crud_activities.get_activity_by_id_from_user_id(activity_id, token_user_id, db)

    # Check if activity is None and raise an HTTPException with a 404 Not Found status code if it is
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity ID {activity_id} for user {token_user_id} not found",
        )
    
    # Delete the activity
    crud_activities.delete_activity(activity_id, db)
    
    # Return success message
    return {"detail": f"Activity {activity_id} deleted successfully"}
    