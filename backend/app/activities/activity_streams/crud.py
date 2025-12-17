from fastapi import HTTPException, status
from sqlalchemy.orm import Session
import numpy as np
import datetime

import activities.activity_streams.constants as activity_streams_constants
import activities.activity_streams.schema as activity_streams_schema
import activities.activity_streams.models as activity_streams_models

import activities.activity.crud as activity_crud
import activities.activity.models as activity_models
import activities.activity.schema as activities_schema

import server_settings.utils as server_settings_utils

import users.user.crud as users_crud

import core.logger as core_logger


def get_activity_streams(
    activity_id: int, token_user_id: int, db: Session
) -> list[activity_streams_schema.ActivityStreams] | None:
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

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
                stream
                for stream in activity_streams
                if not (
                    (
                        activity.hide_hr
                        and stream.stream_type
                        == activity_streams_constants.STREAM_TYPE_HR
                    )
                    or (
                        activity.hide_power
                        and stream.stream_type
                        == activity_streams_constants.STREAM_TYPE_POWER
                    )
                    or (
                        activity.hide_cadence
                        and stream.stream_type
                        == activity_streams_constants.STREAM_TYPE_CADENCE
                    )
                    or (
                        activity.hide_elevation
                        and stream.stream_type
                        == activity_streams_constants.STREAM_TYPE_ELEVATION
                    )
                    or (
                        activity.hide_speed
                        and stream.stream_type
                        == activity_streams_constants.STREAM_TYPE_SPEED
                    )
                    or (
                        activity.hide_pace
                        and stream.stream_type
                        == activity_streams_constants.STREAM_TYPE_PACE
                    )
                    or (
                        activity.hide_map
                        and stream.stream_type
                        == activity_streams_constants.STREAM_TYPE_MAP
                    )
                )
            ]

        # Return the activity streams
        return [
            transform_activity_streams(stream, activity, db)
            for stream in activity_streams
        ]
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


def get_activities_streams(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] = None,
) -> list[activity_streams_schema.ActivityStreams]:
    try:
        if not activity_ids:
            return []

        if not activities:
            activities = (
                db.query(activity_models.Activity)
                .filter(activity_models.Activity.id.in_(activity_ids))
                .all()
            )

        if not activities:
            return []

        # Map: activity_id -> activity
        activity_map = {activity.id: activity for activity in activities}

        # Filter out hidden sets for activities the user doesn't own
        allowed_ids = [
            activity.id for activity in activities if activity.user_id == token_user_id
        ]

        if not allowed_ids:
            return []

        # Fetch all streams for the given activity IDs
        all_streams = (
            db.query(activity_streams_models.ActivityStreams)
            .filter(
                activity_streams_models.ActivityStreams.activity_id.in_(allowed_ids)
            )
            .all()
        )

        if not all_streams:
            return []

        # Transform all allowed streams
        return [
            transform_activity_streams(stream, activity_map[stream.activity_id], db)
            for stream in all_streams
        ]

    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_activities_streams: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_streams(activity_id: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links:
            return None

        activity = activity_crud.get_activity_by_id_if_is_public(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        # Get the activity streams from the database
        activity_streams = (
            db.query(activity_streams_models.ActivityStreams)
            .join(
                activity_models.Activity,
                activity_models.Activity.id
                == activity_streams_models.ActivityStreams.activity_id,
            )
            .filter(
                activity_streams_models.ActivityStreams.activity_id == activity_id,
                activity_models.Activity.visibility == 0,
                activity_models.Activity.id == activity_id,
            )
            .all()
        )

        # Check if there are activity streams, if not return None
        if not activity_streams:
            return None

        activity_streams = [
            stream
            for stream in activity_streams
            if not (
                (
                    activity.hide_hr
                    and stream.stream_type == activity_streams_constants.STREAM_TYPE_HR
                )
                or (
                    activity.hide_power
                    and stream.stream_type
                    == activity_streams_constants.STREAM_TYPE_POWER
                )
                or (
                    activity.hide_cadence
                    and stream.stream_type
                    == activity_streams_constants.STREAM_TYPE_CADENCE
                )
                or (
                    activity.hide_elevation
                    and stream.stream_type
                    == activity_streams_constants.STREAM_TYPE_ELEVATION
                )
                or (
                    activity.hide_speed
                    and stream.stream_type
                    == activity_streams_constants.STREAM_TYPE_SPEED
                )
                or (
                    activity.hide_pace
                    and stream.stream_type
                    == activity_streams_constants.STREAM_TYPE_PACE
                )
                or (
                    activity.hide_map
                    and stream.stream_type == activity_streams_constants.STREAM_TYPE_MAP
                )
            )
        ]

        # Return the activity streams
        return [
            transform_activity_streams(stream, activity, db)
            for stream in activity_streams
        ]
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


def get_activity_stream_by_type(
    activity_id: int, stream_type: int, token_user_id: int, db: Session
):
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

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
            if (
                activity.hide_hr
                and activity_stream.stream_type
                == activity_streams_constants.STREAM_TYPE_HR
            ):
                return None
            if (
                activity.hide_power
                and activity_stream.stream_type
                == activity_streams_constants.STREAM_TYPE_POWER
            ):
                return None
            if (
                activity.hide_cadence
                and activity_stream.stream_type
                == activity_streams_constants.STREAM_TYPE_CADENCE
            ):
                return None
            if (
                activity.hide_elevation
                and activity_stream.stream_type
                == activity_streams_constants.STREAM_TYPE_ELEVATION
            ):
                return None
            if (
                activity.hide_speed
                and activity_stream.stream_type
                == activity_streams_constants.STREAM_TYPE_SPEED
            ):
                return None
            if (
                activity.hide_pace
                and activity_stream.stream_type
                == activity_streams_constants.STREAM_TYPE_PACE
            ):
                return None
            if (
                activity.hide_map
                and activity_stream.stream_type
                == activity_streams_constants.STREAM_TYPE_MAP
            ):
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
    """
    Transforms an activity stream based on its stream type.
    If the stream type of the given activity_stream is heart rate (HR), this function delegates
    the transformation to the `transform_activity_streams_hr` function. Otherwise, it returns
    the activity_stream unchanged.
    Args:
        activity_stream: The activity stream object to be transformed.
        activity: The activity object associated with the stream.
        db: The database session or connection object.
    Returns:
        The transformed activity stream if the stream type is HR, otherwise the original activity_stream.
    """
    if activity_stream.stream_type == activity_streams_constants.STREAM_TYPE_HR:
        return transform_activity_streams_hr(activity_stream, activity, db)

    return activity_stream


def transform_activity_streams_hr(activity_stream, activity, db):
    """
    Transforms an activity stream by calculating the percentage of time spent in each heart rate zone based on user details.
    Args:
        activity_stream: The activity stream object containing waypoints with heart rate data.
        activity: The activity object associated with the stream, used to retrieve the user ID.
        db: The database session or connection used to fetch user details.
    Returns:
        The activity stream object with an added 'hr_zone_percentages' attribute, which contains the percentage of time spent in each heart rate zone and their respective HR boundaries. If waypoi[...]
    Notes:
        - Heart rate zones are calculated using the formula: max_heart_rate = 220 - age.
        - The function expects waypoints to be a list of dicts with an "hr" key.
        - If no valid heart rate data is present, the activity stream is returned as is.
    """
    # Check if the activity stream has waypoints
    waypoints = activity_stream.stream_waypoints
    if not waypoints or not isinstance(waypoints, list):
        # If there are no waypoints, return the activity stream as is
        return activity_stream

    # Get the user details to calculate heart rate zones
    detail_user = users_crud.get_user_by_id(activity.user_id, db)
    if not detail_user:
        # If user details are not available, return the activity stream as is
        return activity_stream

    # Use user's max_heart_rate if set, otherwise calculate based on age formula
    if detail_user.max_heart_rate:
        max_heart_rate = detail_user.max_heart_rate
    elif detail_user.birthdate:
        # Calculate the maximum heart rate based on the user's birthdate
        year = int(detail_user.birthdate.split("-")[0])
        current_year = datetime.datetime.now().year
        max_heart_rate = 220 - (current_year - year)
    else:
        # If neither max_heart_rate nor birthdate is available, return the activity stream as is
        return activity_stream

    # Calculate heart rate zones based on the maximum heart rate
    zone_1 = max_heart_rate * 0.6
    zone_2 = max_heart_rate * 0.7
    zone_3 = max_heart_rate * 0.8
    zone_4 = max_heart_rate * 0.9

    # Extract heart rate values from waypoints
    hr_values = np.array(
        [float(wp.get("hr")) for wp in waypoints if wp.get("hr") is not None]
    )

    # If there are no valid heart rate values, return the activity stream as is
    total = len(hr_values)
    if total == 0:
        return activity_stream

    # Calculate the percentage of time spent in each heart rate zone
    zone_counts = [
        np.sum(hr_values < zone_1),
        np.sum((hr_values >= zone_1) & (hr_values < zone_2)),
        np.sum((hr_values >= zone_2) & (hr_values < zone_3)),
        np.sum((hr_values >= zone_3) & (hr_values < zone_4)),
        np.sum(hr_values >= zone_4),
    ]
    zone_percentages = [
        round((count / total) * 100, 2) for count in zone_counts
    ]

    # Calculate time in seconds for each zone using the percentage
    # of total_timer_time
    has_timer_time = (
        hasattr(activity, "total_timer_time")
        and activity.total_timer_time
    )
    if has_timer_time:
        total_time_seconds = activity.total_timer_time
        zone_time_seconds = [
            int((percent / 100) * total_time_seconds)
            for percent in zone_percentages
        ]
    else:
        # Fallback: no time calculation possible
        zone_time_seconds = [0, 0, 0, 0, 0]

    # Calculate zone HR boundaries for display
    zone_hr = {
        "zone_1": f"< {int(zone_1)}",
        "zone_2": f"{int(zone_1)} - {int(zone_2) - 1}",
        "zone_3": f"{int(zone_2)} - {int(zone_3) - 1}",
        "zone_4": f"{int(zone_3)} - {int(zone_4) - 1}",
        "zone_5": f">= {int(zone_4)}",
    }
    activity_stream.hr_zone_percentages = {
        "zone_1": {
            "percent": zone_percentages[0],
            "hr": zone_hr["zone_1"],
            "time_seconds": zone_time_seconds[0],
        },
        "zone_2": {
            "percent": zone_percentages[1],
            "hr": zone_hr["zone_2"],
            "time_seconds": zone_time_seconds[1],
        },
        "zone_3": {
            "percent": zone_percentages[2],
            "hr": zone_hr["zone_3"],
            "time_seconds": zone_time_seconds[2],
        },
        "zone_4": {
            "percent": zone_percentages[3],
            "hr": zone_hr["zone_4"],
            "time_seconds": zone_time_seconds[3],
        },
        "zone_5": {
            "percent": zone_percentages[4],
            "hr": zone_hr["zone_5"],
            "time_seconds": zone_time_seconds[4],
        },
    }

    return activity_stream


def get_public_activity_stream_by_type(activity_id: int, stream_type: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links:
            return None

        activity = activity_crud.get_activity_by_id_if_is_public(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        # Get the activity stream from the database
        activity_stream = (
            db.query(activity_streams_models.ActivityStreams)
            .join(
                activity_models.Activity,
                activity_models.Activity.id
                == activity_streams_models.ActivityStreams.activity_id,
            )
            .filter(
                activity_streams_models.ActivityStreams.activity_id == activity_id,
                activity_streams_models.ActivityStreams.stream_type == stream_type,
                activity_models.Activity.visibility == 0,
                activity_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if there is an activity stream; if not, return None
        if not activity_stream:
            return None

        if (
            activity.hide_hr
            and activity_stream.stream_type == activity_streams_constants.STREAM_TYPE_HR
        ):
            return None
        if (
            activity.hide_power
            and activity_stream.stream_type
            == activity_streams_constants.STREAM_TYPE_POWER
        ):
            return None
        if (
            activity.hide_cadence
            and activity_stream.stream_type
            == activity_streams_constants.STREAM_TYPE_CADENCE
        ):
            return None
        if (
            activity.hide_elevation
            and activity_stream.stream_type
            == activity_streams_constants.STREAM_TYPE_ELEVATION
        ):
            return None
        if (
            activity.hide_speed
            and activity_stream.stream_type
            == activity_streams_constants.STREAM_TYPE_SPEED
        ):
            return None
        if (
            activity.hide_pace
            and activity_stream.stream_type
            == activity_streams_constants.STREAM_TYPE_PACE
        ):
            return None
        if (
            activity.hide_map
            and activity_stream.stream_type
            == activity_streams_constants.STREAM_TYPE_MAP
        ):
            return None

        # Return the activity stream
        return transform_activity_streams(activity_stream, activity, db)
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
        core_logger.print_to_log_and_console(
            f"Error in create_activity_streams: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
