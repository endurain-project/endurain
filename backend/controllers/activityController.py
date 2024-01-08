"""
API Router for managing user activity information.

This module defines FastAPI routes for performing CRUD operations on user activity records.
It includes endpoints for retrieving, creating, updating, and deleting activity records.
The routes handle user authentication, database interactions using SQLAlchemy,
and provide JSON responses with appropriate metadata.

Endpoints:
- GET /activities/all: Retrieve all user activities.
- GET /activities/useractivities: Retrieve activities for the authenticated user.
- GET /activities/useractivities/{user_id}/week/{week_number}: Retrieve activities for a user in a specific week.
- GET /activities/useractivities/{user_id}/thisweek/distances: Retrieve distances for a user's activities in the current week.
- GET /activities/useractivities/{user_id}/thismonth/distances: Retrieve distances for a user's activities in the current month.
- GET /activities/useractivities/{user_id}/thismonth/number: Retrieve the count of activities for a user in the current month.
- GET /activities/gear/{gearID}: Retrieve activities associated with a specific gear for the authenticated user.
- GET /activities/all/number: Retrieve the total count of all activities.
- GET /activities/useractivities/number: Retrieve the total count of activities for the authenticated user.
- GET /activities/followeduseractivities/number: Retrieve the count of activities for followed users.
- GET /activities/all/pagenumber/{pageNumber}/numRecords/{numRecords}: Retrieve paginated activities for all users.
- GET /activities/useractivities/pagenumber/{pageNumber}/numRecords/{numRecords}: Retrieve paginated activities for the authenticated user.
- GET /activities/followeduseractivities/pagenumber/{pageNumber}/numRecords/{numRecords}: Retrieve paginated activities for followed users.
- GET /activities/{id}: Retrieve details of a specific activity.
- PUT /activities/{activity_id}/addgear/{gear_id}: Associate a gear with a specific activity.
- POST /activities/create: Create a new activity.
- PUT /activities/{activity_id}/deletegear: Disassociate a gear from a specific activity.
- DELETE /activities/{activity_id}/delete: Delete a specific activity.

Dependencies:
- OAuth2PasswordBearer: FastAPI security scheme for handling OAuth2 password bearer tokens.
- get_db_session: Dependency function to get a database session.
- create_error_response: Function to create a standardized error response.
- get_current_user: Dependency function to get the current authenticated user.

Models:
- CreateActivityRequest: Pydantic model for creating activity records.

Functions:
- activity_record_to_dict: Convert Activity SQLAlchemy objects to dictionaries.
- calculate_activity_distances: Calculate distances for different activity types.

Logger:
- Logger named "myLogger" for logging errors and exceptions.

"""
from operator import and_, or_
import logging
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from sqlalchemy import func, desc
from sqlalchemy.orm import joinedload
from db.db import Activity, Follower
from jose import JWTError
from pydantic import BaseModel
from datetime import datetime, timedelta
from . import sessionController
import calendar
from dependencies import get_db_session, create_error_response, get_current_user
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from constants import API_VERSION

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class ActivityBase(BaseModel):
    """
    Pydantic model for representing activity attributes.

    Attributes:
    - distance (int): The distance covered in the activity.
    - name (str): The name of the activity.
    - activity_type (str): The type of activity (e.g., running, cycling).
    - start_time (str): The start time of the activity in ISO 8601 format.
    - end_time (str): The end time of the activity in ISO 8601 format.
    - city (Optional[str]): The city where the activity took place (optional).
    - town (Optional[str]): The town where the activity took place (optional).
    - country (Optional[str]): The country where the activity took place (optional).
    - elevation_gain (int): The elevation gain during the activity.
    - elevation_loss (int): The elevation loss during the activity.
    - pace (float): The pace of the activity.
    - average_speed (float): The average speed during the activity.
    - average_power (int): The average power during the activity.
    - strava_activity_id (Optional[int]): The ID of the activity on Strava (optional).
    """

    distance: int
    name: str
    activity_type: str
    start_time: str
    end_time: str
    city: Optional[str]
    town: Optional[str]
    country: Optional[str]
    elevation_gain: int
    elevation_loss: int
    pace: float
    average_speed: float
    average_power: int
    strava_gear_id: Optional[int]
    strava_activity_id: Optional[int]


class ActivityCreateRequest(ActivityBase):
    """
    Pydantic model for creating activity records.

    Inherits from ActivityBase, which defines the base attributes for activity.

    This class extends the ActivityBase Pydantic model and is specifically tailored for
    creating new activity records.
    """

    pass


# Define a function to convert Activity SQLAlchemy objects to dictionaries
def activity_record_to_dict(record: Activity) -> dict:
    """
    Converts an Activity SQLAlchemy object to a dictionary.

    Parameters:
    - record (Activity): The SQLAlchemy object representing an activity record.

    Returns:
    dict: A dictionary representation of the Activity object.

    This function is used to convert an SQLAlchemy Activity object into a dictionary format for easier serialization and response handling.
    """
    return {
        "id": record.id,
        "user_id": record.user_id,
        "name": record.name,
        "distance": record.distance,
        "activity_type": record.activity_type,
        "start_time": record.start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "end_time": record.end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        "city": record.city,
        "town": record.town,
        "country": record.country,
        "created_at": record.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "elevation_gain": record.elevation_gain,
        "elevation_loss": record.elevation_loss,
        "pace": str(record.pace),
        "average_speed": str(record.average_speed),
        "average_power": record.average_power,
        "visibility": record.visibility,
        "gear_id": record.gear_id,
        "strava_activity_id": record.strava_activity_id,
    }


def calculate_activity_distances(activity_records: List[Activity]) -> dict:
    """
    Calculates the total distances for different activity types.

    Parameters:
    - activity_records (List[Activity]): A list of SQLAlchemy Activity objects representing different activities.

    Returns:
    dict: A dictionary containing the total distances for different activity types.
    The keys include 'run,' 'bike,' and 'swim,' each representing the summed distance for running, biking, and swimming activities, respectively.

    This function iterates through the given list of activity records and categorizes the distances based on the activity type.
    The result is a dictionary with the summed distances for each activity type.
    """

    run = bike = swim = 0

    for activity in activity_records:
        if activity.activity_type in [1, 2, 3]:
            run += activity.distance
        elif activity.activity_type in [4, 5, 6, 7, 8]:
            bike += activity.distance
        elif activity.activity_type == 9:
            swim += activity.distance

    return {"run": run, "bike": bike, "swim": swim}


@router.get("/activities/all", response_model=List[dict])
async def read_activities_all(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Retrieve all activity records.

    Parameters:
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and activity records.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Query the activities records using SQLAlchemy and order by start time
        activity_records = (
            db_session.query(Activity).order_by(desc(Activity.start_time)).all()
        )

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {"total_records": len(activity_records), "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_activities_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/useractivities", response_model=List[dict])
async def read_activities_useractivities(
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve all activities for a specific user.

    Parameters:
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and user-specific activity records.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Query the activities records using SQLAlchemy
        activity_records = (
            db_session.query(Activity)
            .filter(Activity.user_id == user_id)
            .order_by(desc(Activity.start_time))
            .all()
        )

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {"total_records": len(activity_records), "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_activities_useractivities: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/useractivities/{user_id}/week/{week_number}")
async def read_activities_useractivities_thisweek_number(
    user_id: int,
    week_number: int,
    logged_user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve activities for a specific user during a specified week.

    Parameters:
    - user_id (int): The ID of the user for whom activities are being queried.
    - week_number (int): The number of weeks in the past or future to retrieve activities for.
    - logged_user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and user-specific activity records for the specified week.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Calculate the start of the requested week
        today = datetime.utcnow().date()
        start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
        end_of_week = start_of_week + timedelta(days=7)

        # Query the count of activities records for the requested week
        if logged_user_id == user_id:
            activity_records = (
                db_session.query(Activity)
                .filter(
                    Activity.user_id == user_id,
                    func.date(Activity.start_time) >= start_of_week,
                    func.date(Activity.start_time) <= end_of_week,
                )
                .order_by(desc(Activity.start_time))
            ).all()
        else:
            activity_records = (
                db_session.query(Activity)
                .filter(
                    and_(Activity.user_id == user_id, Activity.visibility.in_([0, 1])),
                    func.date(Activity.start_time) >= start_of_week,
                    func.date(Activity.start_time) <= end_of_week,
                )
                .order_by(desc(Activity.start_time))
            ).all()

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {
            "total_records": len(activity_records),
            "user_id": user_id,
            "week_number": week_number,
            "api_version": API_VERSION,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_useractivities_thisweek_number: {err}",
            exc_info=True,
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/useractivities/{user_id}/thisweek/distances")
async def read_activities_useractivities_thisweek_distances(
    user_id=int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve distances covered in activities by a specific user during the current week.

    Parameters:
    - user_id (int): The ID of the user for whom distances are being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing distances covered in activities for the specified user during the current week.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Calculate the start of the current week
        today = datetime.utcnow().date()
        start_of_week = today - timedelta(
            days=today.weekday()
        )  # Monday is the first day of the week, which is denoted by 0
        end_of_week = start_of_week + timedelta(days=7)

        # Query the activities records for the current week
        activity_records = (
            db_session.query(Activity)
            .filter(
                Activity.user_id == user_id,
                func.date(Activity.start_time) >= start_of_week,
                func.date(Activity.start_time) < end_of_week,
            )
            .order_by(desc(Activity.start_time))
            .all()
        )

        # Use the helper function to calculate distances
        distances = calculate_activity_distances(activity_records)

        # Return the queried values using JSONResponse
        # return JSONResponse(content=distances)

        #  Include metadata in the response
        metadata = {"total_records": 1, "user_id": user_id, "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": distances})
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_useractivities_thisweek_distances: {err}",
            exc_info=True,
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/useractivities/{user_id}/thismonth/distances")
async def read_activities_useractivities_thismonth_distances(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve distances covered in activities by a specific user during the current month.

    Parameters:
    - user_id (int): The ID of the user for whom distances are being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing distances covered in activities for the specified user during the current month.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Calculate the start of the current month
        today = datetime.utcnow().date()
        start_of_month = today.replace(day=1)
        end_of_month = start_of_month.replace(
            day=calendar.monthrange(today.year, today.month)[1]
        )

        # Query the activities records for the current month
        activity_records = (
            db_session.query(Activity)
            .filter(
                Activity.user_id == user_id,
                func.date(Activity.start_time) >= start_of_month,
                func.date(Activity.start_time) <= end_of_month,
            )
            .order_by(desc(Activity.start_time))
            .all()
        )

        # Use the helper function to calculate distances
        distances = calculate_activity_distances(activity_records)

        # Return the queried values using JSONResponse
        # return JSONResponse(content=distances)

        #  Include metadata in the response
        metadata = {"total_records": 1, "user_id": user_id, "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": distances})
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_useractivities_thismonth_distances: {err}",
            exc_info=True,
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/useractivities/{user_id}/thismonth/number")
async def read_activities_useractivities_thismonth_number(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the number of activities for a specific user during the current month.

    Parameters:
    - user_id (int): The ID of the user for whom the activity count is being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the number of activities for the specified user during the current month.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Calculate the start of the current month
        today = datetime.utcnow().date()
        start_of_month = today.replace(day=1)
        end_of_month = start_of_month.replace(
            day=calendar.monthrange(today.year, today.month)[1]
        )

        # Query the count of activities records for the current month
        activity_count = (
            db_session.query(func.count(Activity.id))
            .filter(
                Activity.user_id == user_id,
                func.date(Activity.start_time) >= start_of_month,
                func.date(Activity.start_time) <= end_of_month,
            )
            .scalar()
        )

        # Include metadata in the response
        metadata = {"total_records": 1, "user_id": user_id, "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": activity_count})

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_useractivities_thismonth_number: {err}",
            exc_info=True,
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/gear/{gear_id}", response_model=List[dict])
async def read_activities_gearactivities(
    gear_id=int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve activities associated with a specific gear.

    Parameters:
    - gearID (int): The ID of the gear for which activities are being queried.
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and gear-specific activity records.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Query the activities records using SQLAlchemy
        activity_records = (
            db_session.query(Activity)
            .filter(Activity.user_id == user_id, Activity.gear_id == gear_id)
            .order_by(desc(Activity.start_time))
            .all()
        )

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {
            "total_records": len(activity_records),
            "gear_id": gear_id,
            "api_version": API_VERSION,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_activities_gearactivities: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/all/number")
async def read_activities_all_number(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Retrieve the total number of activities.

    Parameters:
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the total number of activities.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Query the number of activities records for the user using SQLAlchemy
        activity_count = db_session.query(func.count(Activity.id)).scalar()

        # Include metadata in the response
        metadata = {"total_records": 1, "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": activity_count})

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_activities_all_number: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/useractivities/number")
async def read_activities_useractivities_number(
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the number of activities for a specific user.

    Parameters:
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the number of activities for the specified user.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Query the number of activities records for the user using SQLAlchemy
        activity_count = (
            db_session.query(func.count(Activity.id))
            .filter(Activity.user_id == user_id)
            .scalar()
        )

        # Include metadata in the response
        metadata = {"total_records": 1, "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": activity_count})

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_useractivities_number: {err}", exc_info=True
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/activities/followeduseractivities/number")
async def read_activities_followed_useractivities_number(
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the number of activities for users followed by the authenticated user.

    Parameters:
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the number of activities for users followed by the authenticated user.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Query the number of activities records for followed users using SQLAlchemy
        activity_count = (
            db_session.query(func.count(Activity.id))
            .join(Follower, Follower.following_id == Activity.user_id)
            .filter(
                and_(
                    Follower.follower_id == user_id,
                    Follower.is_accepted == True,
                ),
                Activity.visibility.in_([0, 1]),
            )
            .scalar()
        )

        # Include metadata in the response
        metadata = {"total_records": 1, "api_version": API_VERSION}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": activity_count})

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_followed_useractivities_number: {err}",
            exc_info=True,
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get(
    "/activities/all/pagenumber/{pageNumber}/numRecords/{numRecords}",
    response_model=List[dict],
)
async def read_activities_all_pagination(
    pageNumber: int,
    numRecords: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve paginated activity records.

    Parameters:
    - pageNumber (int): The page number to retrieve.
    - numRecords (int): The number of records to retrieve per page.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and paginated activity records.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Use SQLAlchemy to query the gear records with pagination
        activity_records = (
            db_session.query(Activity)
            .order_by(desc(Activity.start_time))
            .offset((pageNumber - 1) * numRecords)
            .limit(numRecords)
            .all()
        )

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {
            "total_records": len(activity_records),
            "page_number": pageNumber,
            "num_records": numRecords,
            "api_version": API_VERSION,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_activities_all_pagination: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get(
    "/activities/useractivities/pagenumber/{pageNumber}/numRecords/{numRecords}",
    response_model=List[dict],
)
async def read_activities_useractivities_pagination(
    pageNumber: int,
    numRecords: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve paginated activity records for a specific user.

    Parameters:
    - pageNumber (int): The page number to retrieve.
    - numRecords (int): The number of records to retrieve per page.
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and paginated activity records for the specified user.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Use SQLAlchemy to query the gear records with pagination
        activity_records = (
            db_session.query(Activity)
            .filter(Activity.user_id == user_id)
            .order_by(desc(Activity.start_time))
            .offset((pageNumber - 1) * numRecords)
            .limit(numRecords)
            .all()
        )

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {
            "total_records": len(activity_records),
            "page_number": pageNumber,
            "num_records": numRecords,
            "api_version": API_VERSION,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_useractivities_pagination: {err}", exc_info=True
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get(
    "/activities/followeduseractivities/pagenumber/{pageNumber}/numRecords/{numRecords}",
    response_model=List[dict],
)
async def read_activities_followed_user_activities_pagination(
    pageNumber: int,
    numRecords: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve paginated activity records for users followed by the authenticated user.

    Parameters:
    - pageNumber (int): The page number to retrieve.
    - numRecords (int): The number of records to retrieve per page.
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and paginated activity records for users followed by the authenticated user.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Use SQLAlchemy to query activities of followed users with pagination
        activity_records = (
            db_session.query(Activity)
            .join(Follower, Follower.following_id == Activity.user_id)
            .filter(
                and_(
                    Follower.follower_id == user_id,
                    Follower.is_accepted == True,
                ),
                Activity.visibility.in_([0, 1]),
            )
            .order_by(desc(Activity.start_time))
            .offset((pageNumber - 1) * numRecords)
            .limit(numRecords)
            .options(joinedload(Activity.user))
            .all()
        )

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {
            "total_records": len(activity_records),
            "page_number": pageNumber,
            "num_records": numRecords,
            "api_version": API_VERSION,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(
            f"Error in read_activities_followed_user_activities_pagination: {err}",
            exc_info=True,
        )
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Get gear from id
@router.get("/activities/{id}", response_model=List[dict])
async def read_activities_activityFromId(
    id: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve activity records by ID.

    Parameters:
    - id (int): The ID of the activity to retrieve.
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and activity records for the specified ID.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Use SQLAlchemy to query the gear record by ID
        activity_record = (
            db_session.query(Activity)
            .filter(
                or_(Activity.user_id == user_id, Activity.visibility.in_([0, 1])),
                Activity.id == id,
            )
            .all()
        )

        # Convert the SQLAlchemy result to a list of dictionaries
        if activity_record:
            activity_records = activity_record
        else:
            activity_records = []

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_records_dict = [
            activity_record_to_dict(record) for record in activity_records
        ]

        # Include metadata in the response
        metadata = {
            "total_records": len(activity_records),
            "id": id,
            "api_version": API_VERSION,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_activities_activityFromId: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.put("/activities/{activity_id}/addgear/{gear_id}")
async def activity_add_gear(
    activity_id: int,
    gear_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Add gear to a specific activity.

    Parameters:
    - activity_id (int): The ID of the activity to which gear is being added.
    - gear_id (int): The ID of the gear to add to the activity.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success or failure of adding gear to the activity.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Query the database to find the activity by its ID
        activity_record = db_session.query(Activity).get(activity_id)

        # Check if the activity with the given ID exists
        if activity_record:
            # Set the activity's gear ID to the given gear ID
            activity_record.gear_id = gear_id

            # Commit the transaction
            db_session.commit()

            # Return a success response
            return JSONResponse(
                content={"message": "Gear added to activity successfully"},
                status_code=200,
            )
        else:
            # Return a 404 response if the activity with the given ID does not exist
            return create_error_response("NOT_FOUND", "Activity not found", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in activity_add_gear: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.post("/activities/create")
async def create_activity(
    activity_data: ActivityCreateRequest,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Create a new activity.

    Parameters:
    - activity_data (ActivityCreateRequest): Data for creating a new activity.
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success or failure of creating the activity.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Convert the 'starttime' string to a datetime
        starttime = parse_timestamp(activity_data.start_time)
        # Convert the 'endtime' string to a datetime
        endtime = parse_timestamp(activity_data.end_time)

        auxType = 10  # Default value
        type_mapping = {
            "Run": 1,
            "running": 1,
            "trail running": 2,
            "TrailRun": 2,
            "VirtualRun": 3,
            "cycling": 4,
            "Ride": 4,
            "GravelRide": 5,
            "EBikeRide": 6,
            "VirtualRide": 7,
            "virtual_ride": 7,
            "swimming": 8,
            "open_water_swimming": 8,
            "Walk": 9,
        }
        # "AlpineSki",
        # "BackcountrySki",
        # "Badminton",
        # "Canoeing",
        # "Crossfit",
        # "EBikeRide",
        # "Elliptical",
        # "EMountainBikeRide",
        # "Golf",
        # "GravelRide",
        # "Handcycle",
        # "HighIntensityIntervalTraining",
        # "Hike",
        # "IceSkate",
        # "InlineSkate",
        # "Kayaking",
        # "Kitesurf",
        # "MountainBikeRide",
        # "NordicSki",
        # "Pickleball",
        # "Pilates",
        # "Racquetball",
        # "Ride",
        # "RockClimbing",
        # "RollerSki",
        # "Rowing",
        # "Run",
        # "Sail",
        # "Skateboard",
        # "Snowboard",
        # "Snowshoe",
        # "Soccer",
        # "Squash",
        # "StairStepper",
        # "StandUpPaddling",
        # "Surfing",
        # "Swim",
        # "TableTennis",
        # "Tennis",
        # "TrailRun",
        # "Velomobile",
        # "VirtualRide",
        # "VirtualRow",
        # "VirtualRun",
        # "Walk",
        # "WeightTraining",
        # "Wheelchair",
        # "Windsurf",
        # "Workout",
        # "Yoga"
        auxType = type_mapping.get(activity_data.activity_type, 10)

        # Create a new Activity record
        activity = Activity(
            user_id=user_id,
            name=activity_data.name,
            distance=activity_data.distance,
            activity_type=auxType,
            start_time=starttime,
            end_time=endtime,
            city=activity_data.city,
            town=activity_data.town,
            country=activity_data.country,
            created_at=func.now(),  # Use func.now() to set 'created_at' to the current timestamp
            elevation_gain=activity_data.elevation_gain,
            elevation_loss=activity_data.elevation_loss,
            pace=activity_data.pace,
            average_speed=activity_data.average_speed,
            average_power=activity_data.average_power,
            strava_gear_id=activity_data.strava_gear_id,
            strava_activity_id=activity_data.strava_activity_id,
        )

        # Store the Activity record in the database
        db_session.add(activity)
        db_session.commit()
        db_session.refresh(activity)

        # Return a JSONResponse indicating the success of the activity creation
        return JSONResponse(
            content={"message": "Activity created successfully", "activity_id": activity.id},
            status_code=201,
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in create_activity: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def parse_timestamp(timestamp_string):
    """
    Parse a timestamp string into a datetime object.

    Parameters:
    - timestamp_string (str): The timestamp string to be parsed.

    Returns:
    - datetime: The parsed datetime object.
    """
    try:
        # Try to parse with milliseconds
        return datetime.strptime(timestamp_string, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        # If milliseconds are not present, use a default value of 0
        return datetime.strptime(timestamp_string, "%Y-%m-%dT%H:%M:%SZ")


# Define an HTTP PUT route to delete an activity gear
@router.put("/activities/{activity_id}/deletegear")
async def delete_activity_gear(
    activity_id: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Delete gear associated with a specific activity.

    Parameters:
    - activity_id (int): The ID of the activity from which gear is being deleted.
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success or failure of deleting gear from the activity.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Query the database to find the user by their ID
        activity = (
            db_session.query(Activity)
            .filter(Activity.id == activity_id, Activity.user_id == user_id)
            .first()
        )

        # Check if the user with the given ID exists
        if not activity:
            # Return a 404 response if the user with the given ID does not exist
            return create_error_response("NOT_FOUND", "Activity not found", 404)

        # Set the user's photo paths to None to delete the photo
        activity.gear_id = None

        # Commit the changes to the database
        db_session.commit()

        # Return a success response
        return JSONResponse(
            content={"message": "Gear deleted from activity successfully"},
            status_code=200,
        )
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in delete_activity_gear: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.delete("/activities/{activity_id}/delete")
async def delete_activity(
    activity_id: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Delete a specific activity.

    Parameters:
    - activity_id (int): The ID of the activity to be deleted.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success or failure of deleting the activity.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Use SQLAlchemy to query and delete the gear record
        activity_record = (
            db_session.query(Activity)
            .filter(Activity.id == activity_id, Activity.user_id == user_id)
            .first()
        )

        if activity_record:
            # Delete the gear record
            db_session.delete(activity_record)

            # Commit the transaction
            db_session.commit()

            # Return a success response
            return JSONResponse(
                content={"message": f"Activity {activity_id} has been deleted"},
                status_code=200,
            )
        else:
            # Return a 404 response if the gear with the given ID does not exist
            return create_error_response("NOT_FOUND", "Activity not found", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in delete_activity: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )
