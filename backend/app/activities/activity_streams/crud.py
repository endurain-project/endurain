from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import numpy as np
import datetime

import activities.activity_streams.schema as activity_streams_schema
import activities.activity_streams.models as activity_streams_models

import activities.activity.crud as activity_crud

import activities.activity.models as activities_models

import server_settings.crud as server_settings_crud

import users.user.crud as users_crud

import core.logger as core_logger

import activities.activity_streams.constants as stream_constants


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
                    (activity.hide_hr and stream.stream_type == stream_constants.STREAM_TYPE_HR) or
                    (activity.hide_power and stream.stream_type == stream_constants.STREAM_TYPE_POWER) or
                    (activity.hide_cadence and stream.stream_type == stream_constants.STREAM_TYPE_CADENCE) or
                    (activity.hide_elevation and stream.stream_type == stream_constants.STREAM_TYPE_ELEVATION) or
                    (activity.hide_speed and stream.stream_type == stream_constants.STREAM_TYPE_SPEED) or
                    (activity.hide_pace and stream.stream_type == stream_constants.STREAM_TYPE_PACE) or
                    (activity.hide_map and stream.stream_type == stream_constants.STREAM_TYPE_MAP)
                )
            ]

        # Return the activity streams
        return [transform_activity_streams(stream, activity, db) for stream in activity_streams]
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
                (activity.hide_hr and stream.stream_type == stream_constants.STREAM_TYPE_HR) or
                (activity.hide_power and stream.stream_type == stream_constants.STREAM_TYPE_POWER) or
                (activity.hide_cadence and stream.stream_type == stream_constants.STREAM_TYPE_CADENCE) or
                (activity.hide_elevation and stream.stream_type == stream_constants.STREAM_TYPE_ELEVATION) or
                (activity.hide_speed and stream.stream_type == stream_constants.STREAM_TYPE_SPEED) or
                (activity.hide_pace and stream.stream_type == stream_constants.STREAM_TYPE_PACE) or
                (activity.hide_map and stream.stream_type == stream_constants.STREAM_TYPE_MAP)
            )
        ]

        # Return the activity streams
        return [transform_activity_streams(stream, activity, db) for stream in activity_streams]
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
            if activity.hide_hr and activity_stream.stream_type == stream_constants.STREAM_TYPE_HR:
                return None
            if activity.hide_power and activity_stream.stream_type == stream_constants.STREAM_TYPE_POWER:
                return None
            if activity.hide_cadence and activity_stream.stream_type == stream_constants.STREAM_TYPE_CADENCE:
                return None
            if activity.hide_elevation and activity_stream.stream_type == stream_constants.STREAM_TYPE_ELEVATION:
                return None
            if activity.hide_speed and activity_stream.stream_type == stream_constants.STREAM_TYPE_SPEED:
                return None
            if activity.hide_pace and activity_stream.stream_type == stream_constants.STREAM_TYPE_PACE:
                return None
            if activity.hide_map and activity_stream.stream_type == stream_constants.STREAM_TYPE_MAP:
                return None

        # Return the activity stream
        return transform_activity_streams(activity_stream, activity, db)
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

def transform_activity_streams(activity_stream, activity, db):
    print("Transforming activity stream")
    """
    Transform the activity stream based on the stream type.
    """
    if activity_stream.stream_type == stream_constants.STREAM_TYPE_HR:
        return transform_activity_streams_hr(activity_stream, activity, db)
    else:
        return activity_stream

def transform_activity_streams_hr(activity_stream, activity, db):
    print("Transforming HR activity stream")
    """
    Transform the activity stream for heart rate.
    Calculate the percentage of time spent in each HR zone using numpy for performance.
    """
    detail_user = users_crud.get_user_by_id(activity.user_id, db)
    print(f"Detail user: {detail_user}")
    if not detail_user or not detail_user.birthdate:
        return activity_stream
    year = int(detail_user.birthdate.split("-")[0])
    current_year = datetime.datetime.now().year
    max_heart_rate = 220 - (current_year - year)
    print(f"Max heart rate: {max_heart_rate}")

    zone_1 = max_heart_rate * 0.5
    zone_2 = max_heart_rate * 0.6
    zone_3 = max_heart_rate * 0.7
    zone_4 = max_heart_rate * 0.8
    print(f"Heart rate zones: {zone_1}, {zone_2}, {zone_3}, {zone_4}")

    waypoints = activity_stream.stream_waypoints
    if not waypoints or not isinstance(waypoints, list):
        return activity_stream
    
    hr_values = np.array([wp.get("hr") for wp in waypoints if wp.get("hr") is not None])

    total = len(hr_values)
    print(f"Total HR values: {total}")

    if total == 0:
        return activity_stream
    
    zone_counts = [
        np.sum(hr_values < zone_1),
        np.sum((hr_values >= zone_1) & (hr_values < zone_2)),
        np.sum((hr_values >= zone_2) & (hr_values < zone_3)),
        np.sum((hr_values >= zone_3) & (hr_values < zone_4)),
        np.sum(hr_values >= zone_4),
    ]
    zone_percentages = [round((count / total) * 100, 2) for count in zone_counts]

    # Calculate zone HR boundaries for display
    zone_hr = {
        "zone_1": f"< {int(zone_1)}",
        "zone_2": f"{int(zone_1)} - {int(zone_2) - 1}",
        "zone_3": f"{int(zone_2)} - {int(zone_3) - 1}",
        "zone_4": f"{int(zone_3)} - {int(zone_4) - 1}",
        "zone_5": f">= {int(zone_4)}",
    }
    activity_stream.hr_zone_percentages = {
        "zone_1": {"percent": zone_percentages[0], "hr": zone_hr["zone_1"]},
        "zone_2": {"percent": zone_percentages[1], "hr": zone_hr["zone_2"]},
        "zone_3": {"percent": zone_percentages[2], "hr": zone_hr["zone_3"]},
        "zone_4": {"percent": zone_percentages[3], "hr": zone_hr["zone_4"]},
        "zone_5": {"percent": zone_percentages[4], "hr": zone_hr["zone_5"]},
    }

    print(f"HR zone percentages: {activity_stream.hr_zone_percentages}")

    return activity_stream

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
        
        if activity.hide_hr and activity_stream.stream_type == stream_constants.STREAM_TYPE_HR:
            return None
        if activity.hide_power and activity_stream.stream_type == stream_constants.STREAM_TYPE_POWER:
            return None
        if activity.hide_cadence and activity_stream.stream_type == stream_constants.STREAM_TYPE_CADENCE:
            return None
        if activity.hide_elevation and activity_stream.stream_type == stream_constants.STREAM_TYPE_ELEVATION:
            return None
        if activity.hide_speed and activity_stream.stream_type == stream_constants.STREAM_TYPE_SPEED:
            return None
        if activity.hide_pace and activity_stream.stream_type == stream_constants.STREAM_TYPE_PACE:
            return None
        if activity.hide_map and activity_stream.stream_type == stream_constants.STREAM_TYPE_MAP:
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
