from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.models as activity_models
import activities.activity.crud as activity_crud

import activities.activity_laps.models as activity_laps_models
import activities.activity_laps.schema as activity_laps_schema
import activities.activity_laps.utils as activity_laps_utils

import server_settings.utils as server_settings_utils

import core.logger as core_logger


def get_activity_laps(activity_id: int, token_user_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        user_is_owner = True
        if token_user_id != activity.user_id:
            user_is_owner = False

        if not user_is_owner and activity.hide_laps:
            # If the user is not the owner and laps are hidden, return None
            return None

        # Get the activity laps from the database
        activity_laps = (
            db.query(activity_laps_models.ActivityLaps)
            .filter(
                activity_laps_models.ActivityLaps.activity_id == activity_id,
            )
            .all()
        )

        # Check if there are activity laps if not return None
        if not activity_laps:
            return None

        # Serialize the activity laps
        for lap in activity_laps:
            lap = activity_laps_utils.serialize_activity_lap(activity, lap)

        # Return the activity laps
        return activity_laps
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_activity_laps: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activities_laps(
    activity_ids: list[int],
    token_user_id: int,
    db: Session,
    activities: list[activities_schema.Activity] = None,
):
    try:
        if not activity_ids:
            return []

        if not activities:
            # Fetch all activities at once
            activities = (
                db.query(activity_models.Activity)
                .filter(activity_models.Activity.id.in_(activity_ids))
                .all()
            )

        if not activities:
            return []

        # Build a map of activity_id -> activity
        activity_map = {activity.id: activity for activity in activities}

        # Filter out hidden laps for activities the user doesn't own
        allowed_ids = [
            activity.id for activity in activities if activity.user_id == token_user_id
        ]

        if not allowed_ids:
            return []

        # Fetch all laps for allowed activities
        activity_laps = (
            db.query(activity_laps_models.ActivityLaps)
            .filter(activity_laps_models.ActivityLaps.activity_id.in_(allowed_ids))
            .all()
        )

        if not activity_laps:
            return []

        # Serialize each lap
        serialized_laps = [
            activity_laps_utils.serialize_activity_lap(
                activity_map[lap.activity_id], lap
            )
            for lap in activity_laps
        ]

        return serialized_laps

    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_activities_laps: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_laps(activity_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        if activity.hide_laps:
            # If the user is not the owner and laps are hidden, return None
            return None

        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links:
            return None

        # Get the activity laps from the database
        activity_laps = (
            db.query(activity_laps_models.ActivityLaps)
            .join(
                activity_models.Activity,
                activity_models.Activity.id
                == activity_laps_models.ActivityLaps.activity_id,
            )
            .filter(
                activity_laps_models.ActivityLaps.activity_id == activity_id,
                activity_models.Activity.visibility == 0,
                activity_models.Activity.id == activity_id,
            )
            .all()
        )

        # Check if there are activity laps, if not return None
        if not activity_laps:
            return None

        # Serialize the activity laps
        for lap in activity_laps:
            lap = activity_laps_utils.serialize_activity_lap(activity, lap)

        # Return the activity laps
        return activity_laps
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_public_activity_laps: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity_laps(
    activity_laps: list[activity_laps_schema.ActivityLaps],
    activity_id: int,
    db: Session,
):
    try:
        # Create a list to store the ActivityLaps objects
        laps = []

        # Iterate over the list of ActivityLaps objects
        for lap in activity_laps:
            # Create an ActivityLaps object
            db_stream = activity_laps_models.ActivityLaps(
                activity_id=activity_id,
                **{
                    key: lap.get(key)
                    for key in [
                        "start_time",
                        "start_position_lat",
                        "start_position_long",
                        "end_position_lat",
                        "end_position_long",
                        "total_elapsed_time",
                        "total_timer_time",
                        "total_distance",
                        "total_cycles",
                        "total_calories",
                        "avg_heart_rate",
                        "max_heart_rate",
                        "avg_cadence",
                        "max_cadence",
                        "avg_power",
                        "max_power",
                        "total_ascent",
                        "total_descent",
                        "intensity",
                        "lap_trigger",
                        "sport",
                        "sub_sport",
                        "normalized_power",
                        "total_work",
                        "avg_vertical_oscillation",
                        "avg_stance_time",
                        "avg_fractional_cadence",
                        "max_fractional_cadence",
                        "enhanced_avg_pace",
                        "enhanced_avg_speed",
                        "enhanced_max_pace",
                        "enhanced_max_speed",
                        "enhanced_min_altitude",
                        "enhanced_max_altitude",
                        "avg_vertical_ratio",
                        "avg_step_length",
                    ]
                },
            )

            # Append the object to the list
            laps.append(db_stream)

        # Bulk insert the list of ActivityLaps objects
        db.bulk_save_objects(laps)
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger(f"Error in create_activity_laps: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
