import os
import logging
import calendar

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from schemas import (
    activities as activities_schema,
    access_tokens as access_tokens_schema,
)
from crud import activities as activities_crud
from dependencies import get_db

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get(
    "/activities/{user_id}/week/{week_number}",
    response_model=list[activities_schema.Activity],
    tags=["activities"],
)
async def read_activities_useractivities_week(
    user_id: int,
    week_number: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the activities for the requested week for the user or the users that the user is following"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Check if week number is higher or equal than 0
    if not (int(week_number) >= 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid week number",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Calculate the start of the requested week
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
    end_of_week = start_of_week + timedelta(days=7)

    if user_id == access_tokens_schema.get_token_user_id(token):
        # Get all user activities for the requested week if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )
    else:
        # Get user following activities for the requested week if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_week, end_of_week, db
        )

    # Return the activities
    return activities


@router.get(
    "/activities/{user_id}/thisweek/distances",
    response_model=activities_schema.ActivityDistances | None,
    tags=["activities"],
)
async def read_activities_useractivities_thisweek_distances(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the distances of the activities for the requested week for the user or the users that the user is following"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Calculate the start of the current week
    today = datetime.utcnow().date()
    start_of_week = today - timedelta(
        days=today.weekday()
    )  # Monday is the first day of the week, which is denoted by 0
    end_of_week = start_of_week + timedelta(days=7)

    if user_id == access_tokens_schema.get_token_user_id(token):
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

    # Return the activities distances for this week
    return activities_schema.calculate_activity_distances(activities)


@router.get(
    "/activities/{user_id}/thismonth/distances",
    response_model=activities_schema.ActivityDistances | None,
    tags=["activities"],
)
async def read_activities_useractivities_thismonth_distances(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the distances of the activities for the requested month for the user or the users that the user is following"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Calculate the start of the current month
    today = datetime.utcnow().date()
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )

    if user_id == access_tokens_schema.get_token_user_id(token):
        # Get all user activities for the requested month if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )
    else:
        # Get user following activities for the requested month if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )

    if activities is None:
        # Return None if activities is None
        return None

    # Return the activities distances for this month
    return activities_schema.calculate_activity_distances(activities)


@router.get(
    "/activities/{user_id}/thismonth/number",
    response_model=int,
    tags=["activities"],
)
async def read_activities_useractivities_thismonth_number(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the number of activities for the requested month for the user or the users that the user is following"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Calculate the start of the current month
    today = datetime.utcnow().date()
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )

    if user_id == access_tokens_schema.get_token_user_id(token):
        # Get all user activities for the requested month if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )
    else:
        # Get user following activities for the requested month if the user is not the owner of the token
        activities = activities_crud.get_user_following_activities_per_timeframe(
            user_id, start_of_month, end_of_month, db
        )

    return len(activities)


@router.get(
    "/activities/{user_id}/number",
    response_model=int,
    tags=["activities"],
)
async def read_activities_useractivities_number(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Get the number of activities for the user
    activities = activities_crud.get_user_activities(user_id, db)

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/activities/{user_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,
    tags=["activities"],
)
async def read_activities_useractivities_pagination(
    user_id: int,
    page_number: int,
    num_records: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the activities for the user with pagination"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )
    
    # Check if page_number higher than 0
    if not (int(page_number) > 0):
        # Raise an HTTPException with a 422 Unprocessable Entity status code
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Page Number",
        )

    # Check if num_records higher than 0
    if not (int(num_records) > 0):
        # Raise an HTTPException with a 422 Unprocessable Entity status code
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Number of Records",
        )
    
    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Get the activities for the user with pagination
    activities = activities_crud.get_user_activities_with_pagination(user_id, db, page_number, num_records)

    # Check if activities is None and return None if it is
    if activities is None:
        return None

    # Return activities
    return activities

@router.post("/activities/{user_id}/create/upload")
async def create_activity_with_uploaded_file(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )
    
    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

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
            parsed_info = parse_gpx_file(file.filename, user_id)
        elif file_extension.lower() == ".fit":
            parsed_info = parse_fit_file(file.filename, user_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_406_NOT_ACCEPTABLE,
                detail="File extension not supported. Supported file extensions are .gpx and .fit",
            )

    except Exception as err:
        # Log the exception
        logger.error(f"Error in create_activity_with_uploaded_file: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    