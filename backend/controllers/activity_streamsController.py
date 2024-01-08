"""
API Router for managing activity stream information.

This module defines FastAPI routes for performing CRUD operations on activity stream records.
It includes endpoints for retrieving and creating activity stream records.
The routes handle user authentication, database interactions using SQLAlchemy,
and provide JSON responses with appropriate metadata.

Endpoints:
- GET /activities/streams/activity_id/{activity_id}/all: Retrieve all activity streams for a specific activity.
- POST /activities/streams/create: Create a new activity stream record.

Dependencies:
- OAuth2PasswordBearer: FastAPI security scheme for handling OAuth2 password bearer tokens.
- get_db_session: Dependency function to get a database session.
- create_error_response: Function to create a standardized error response.

Models:
- ActivityStreamBase: Pydantic model for representing activity stream attributes.
- ActivityStreamCreateRequest: Pydantic model for creating activity stream records.

Functions:
- activity_streams_records_to_dict: Convert ActivityStreams SQLAlchemy objects to dictionaries.

Logger:
- Logger named "myLogger" for logging errors and exceptions.

Routes:
- read_activities_streams_for_activity_all: Retrieve all activity streams for a specific activity.
- create_activity_stream: Create a new activity stream record.
"""
import logging
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from db.db import ActivityStreams
from jose import JWTError
from pydantic import BaseModel
from . import sessionController
from dependencies import get_db_session, create_error_response
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from constants import API_VERSION

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class ActivityStreamBase(BaseModel):
    """
    Pydantic model for representing activity attributes.

    Attributes:
    - activity_id (int): The activity this activity stream belongs.
    - stream_type (str): The stream type.
    - stream_waypoints (List[dict]): List of waypoints for the activity stream, typically contains datetime and specify stream like HR, Power, etc.
    - strava_activity_stream_id (Optional[int]): The ID of the activity stream on Strava (optional).
    """
    activity_id: int
    stream_type: str
    stream_waypoints: List[dict]
    strava_activity_stream_id: Optional[int]


class ActivityStreamCreateRequest(ActivityStreamBase):
    """
    Pydantic model for creating activity stream records.

    Inherits from ActivityStreamBase, which defines the base attributes for activity stream.

    This class extends the ActivityStreamBase Pydantic model and is specifically tailored for
    creating new activity stream records.
    """
    pass


# Define a function to convert Activity SQLAlchemy objects to dictionaries
def activity_streams_records_to_dict(record: ActivityStreams) -> dict:
    """
    Converts an ActivityStreams SQLAlchemy object to a dictionary.

    Parameters:
    - record (ActivityStreams): The SQLAlchemy object representing an activity stream record.

    Returns:
    dict: A dictionary representation of the ActivityStreams object.

    This function is used to convert an SQLAlchemy ActivityStreams object into a dictionary format for easier serialization and response handling.
    """
    return {
        "id": record.id,
        "activity_id": record.activity_id,
        "stream_type": record.stream_type,
        "stream_waypoints": record.stream_waypoints,
        "strava_activity_stream_id": record.strava_activity_stream_id,
    }


@router.get("/activities/streams/activity_id/{activity_id}/all", response_model=List[dict])
async def read_activities_streams_for_activity_all(
    activity_id=int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve all activity streams for a specific activity.

    Parameters:
    - activity_id (int): The ID of the activity for which to retrieve streams.
    - token (str): OAuth2 bearer token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and activity stream records.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the token
        sessionController.validate_token(db_session, token)

        # Query the activities streams records using SQLAlchemy
        activity_streams_records = (
            db_session.query(ActivityStreams)
            .filter(ActivityStreams.activity_id == activity_id)
            .all()
        )

        # Use the activity_record_to_dict function to convert SQLAlchemy objects to dictionaries
        activity_streams_records_dict = [
            activity_streams_records_to_dict(record)
            for record in activity_streams_records
        ]

        # Include metadata in the response
        metadata = {
            "total_records": len(activity_streams_records),
            "api_version": API_VERSION,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": activity_streams_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_activities_streams_for_activity_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )

@router.post("/activities/streams/create")
async def create_activity_stream(
    activity_stream_data: ActivityStreamCreateRequest,
    db_session: Session = Depends(get_db_session),
):
    """
    Create a new activity stream record.

    Parameters:
    - activity_stream_data (ActivityStreamCreateRequest): Pydantic model representing the data for creating a new activity stream.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of the activity stream creation.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Create a new Activity record
        activity_stream = ActivityStreams(
            activity_id=activity_stream_data.activity_id,
            stream_type=activity_stream_data.stream_type,
            stream_waypoints=activity_stream_data.stream_waypoints,
            strava_activity_stream_id=activity_stream_data.strava_activity_stream_id,
        )

        # Store the Activity record in the database
        db_session.add(activity_stream)
        db_session.commit()
        db_session.refresh(activity_stream)

        # Return a JSONResponse indicating the success of the activity creation
        return JSONResponse(
            content={"message": "Activity stream created successfully"},
            status_code=201,
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in create_activity_stream: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )