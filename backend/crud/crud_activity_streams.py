import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from schemas import schema_activity_streams
import models

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_activity_streams(activity_id: int, db: Session):
    try:
        # Get the activity streams from the database
        activity_streams = (
            db.query(models.ActivityStreams)
            .filter(
                models.ActivityStreams.activity_id == activity_id,
            )
            .all()
        )

        # Check if there are activity streams if not return None
        if not activity_streams:
            return None

        # Return the activity streams
        return activity_streams
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_activity_streams: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_stream_by_type(activity_id: int, stream_type: int, db: Session):
    """
    Retrieve activity streams by activity ID and stream type from the database.

    Args:
        activity_id (int): The ID of the activity.
        stream_type (int): The type of the stream.
        db (Session): The database session.

    Returns:
        List[ActivityStreams] or None: A list of activity streams matching the given activity ID and stream type,
        or None if no activity streams are found.

    Raises:
        HTTPException: If there is an error retrieving the activity streams from the database.
    """
    try:
        # Get the activity stream from the database
        activity_stream = (
            db.query(models.ActivityStreams)
            .filter(
                models.ActivityStreams.activity_id == activity_id,
                models.ActivityStreams.stream_type == stream_type,
            )
            .first()
        )

        # Check if there are activity stream if not return None
        if not activity_stream:
            return None

        # Return the activity stream
        return activity_stream
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_activity_stream_by_type: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity_streams(
    activity_streams: [schema_activity_streams.ActivityStreams], db: Session
):
    """
    Create a list of ActivityStreams objects in the database.

    Args:
        activity_streams (list): A list of ActivityStreams objects.
        db (Session): The database session.

    Raises:
        HTTPException: If there is an internal server error.

    Returns:
        None
    """
    try:
        # Create a list to store the ActivityStreams objects
        streams = []

        # Iterate over the list of ActivityStreams objects
        for stream in activity_streams:
            # Create an ActivityStreams object
            db_stream = models.ActivityStreams(
                activity_id=stream.activity_id,
                stream_type=stream.stream_type,
                stream_waypoints=stream.stream_waypoints,
                strava_activity_stream_id=stream.strava_activity_stream_id,
            )

            # Append the object to the list
            streams.append(db_stream)

        # Bulk insert the list of ActivityStreams objects
        db.bulk_save_objects(streams)
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        logger.error(f"Error in create_activity_streams: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
