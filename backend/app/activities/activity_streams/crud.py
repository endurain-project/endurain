from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity_streams.schema as activity_streams_schema
import activities.activity_streams.models as activity_streams_models

import activities.activity.crud as activity_crud

import activities.activity.models as activities_models

import server_settings.crud as server_settings_crud

import core.logger as core_logger


def get_activity_streams(activity_id: int, token_user_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(
            activity_id, db
        )

        if not activity:
            # If the activity does not exist, return None
            return None

        # Get the activity streams from the database
        activity_streams = (
            db.query(activity_streams_models.ActivityStreams)
            .filter(
                activity_streams_models.ActivityStreams.activity_id == activity_id,
            )
            .all()
        )

        # Check if there are activity streams if not return None
        if not activity_streams:
            return None

        user_is_owner = True
        if token_user_id != activity.user_id:
            user_is_owner = False

        if not user_is_owner:
            activity_streams = [
                stream for stream in activity_streams
                if not (
                    (activity.hide_hr and stream.stream_type == 1) or
                    (activity.hide_power and stream.stream_type == 2) or
                    (activity.hide_cadence and stream.stream_type == 3) or
                    (activity.hide_elevation and stream.stream_type == 4) or
                    (activity.hide_speed and stream.stream_type == 5) or
                    (activity.hide_pace and stream.stream_type == 6) or
                    (activity.hide_map and stream.stream_type == 7)
                )
            ]

        # Return the activity streams
        return activity_streams
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_streams: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_streams(activity_id: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_crud.get_server_settings(db)

        # Return None if public sharable links are disabled
        if not server_settings or not server_settings.public_shareable_links:
            return None
        
        activity = activity_crud.get_activity_by_id_if_is_public(
            activity_id, db
        )

        if not activity:
            # If the activity does not exist, return None
            return None

        # Get the activity streams from the database
        activity_streams = (
            db.query(activity_streams_models.ActivityStreams)
            .join(
                activities_models.Activity,
                activities_models.Activity.id
                == activity_streams_models.ActivityStreams.activity_id,
            )
            .filter(
                activity_streams_models.ActivityStreams.activity_id == activity_id,
                activities_models.Activity.visibility == 0,
                activities_models.Activity.id == activity_id,
            )
            .all()
        )

        # Check if there are activity streams, if not return None
        if not activity_streams:
            return None
        
        activity_streams = [
            stream for stream in activity_streams
            if not (
                (activity.hide_hr and stream.stream_type == 1) or
                (activity.hide_power and stream.stream_type == 2) or
                (activity.hide_cadence and stream.stream_type == 3) or
                (activity.hide_elevation and stream.stream_type == 4) or
                (activity.hide_speed and stream.stream_type == 5) or
                (activity.hide_pace and stream.stream_type == 6) or
                (activity.hide_map and stream.stream_type == 7)
            )
        ]

        # Return the activity streams
        return activity_streams
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_public_activity_streams: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_stream_by_type(activity_id: int, stream_type: int, token_user_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(
            activity_id, db
        )

        if not activity:
            # If the activity does not exist, return None
            return None
        
        # Get the activity stream from the database
        activity_stream = (
            db.query(activity_streams_models.ActivityStreams)
            .filter(
                activity_streams_models.ActivityStreams.activity_id == activity_id,
                activity_streams_models.ActivityStreams.stream_type == stream_type,
            )
            .first()
        )

        # Check if there are activity stream if not return None
        if not activity_stream:
            return None
        
        user_is_owner = True
        if token_user_id != activity.user_id:
            user_is_owner = False

        if not user_is_owner:
            if activity.hide_hr and activity_stream.stream_type == 1:
                return None
            if activity.hide_power and activity_stream.stream_type == 2:
                return None
            if activity.hide_cadence and activity_stream.stream_type == 3:
                return None
            if activity.hide_elevation and activity_stream.stream_type == 4:
                return None
            if activity.hide_speed and activity_stream.stream_type == 5:
                return None
            if activity.hide_pace and activity_stream.stream_type == 6:
                return None
            if activity.hide_map and activity_stream.stream_type == 7:
                return None

        # Return the activity stream
        return activity_stream
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_stream_by_type: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_stream_by_type(activity_id: int, stream_type: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_crud.get_server_settings(db)

        # Return None if public sharable links are disabled
        if not server_settings or not server_settings.public_shareable_links:
            return None
        
        activity = activity_crud.get_activity_by_id_if_is_public(
            activity_id, db
        )

        if not activity:
            # If the activity does not exist, return None
            return None

        # Get the activity stream from the database
        activity_stream = (
            db.query(activity_streams_models.ActivityStreams)
            .join(
                activities_models.Activity,
                activities_models.Activity.id
                == activity_streams_models.ActivityStreams.activity_id,
            )
            .filter(
                activity_streams_models.ActivityStreams.activity_id == activity_id,
                activity_streams_models.ActivityStreams.stream_type == stream_type,
                activities_models.Activity.visibility == 0,
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if there is an activity stream; if not, return None
        if not activity_stream:
            return None
        
        if activity.hide_hr and activity_stream.stream_type == 1:
            return None
        if activity.hide_power and activity_stream.stream_type == 2:
            return None
        if activity.hide_cadence and activity_stream.stream_type == 3:
            return None
        if activity.hide_elevation and activity_stream.stream_type == 4:
            return None
        if activity.hide_speed and activity_stream.stream_type == 5:
            return None
        if activity.hide_pace and activity_stream.stream_type == 6:
            return None
        if activity.hide_map and activity_stream.stream_type == 7:
            return None

        # Return the activity stream
        return activity_stream
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_public_activity_stream_by_type: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity_streams(
    activity_streams: list[activity_streams_schema.ActivityStreams], db: Session
):
    try:
        # Create a list to store the ActivityStreams objects
        streams = []

        # Iterate over the list of ActivityStreams objects
        for stream in activity_streams:
            # Create an ActivityStreams object
            db_stream = activity_streams_models.ActivityStreams(
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
        core_logger(f"Error in create_activity_streams: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
