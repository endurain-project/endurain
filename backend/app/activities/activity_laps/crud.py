from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity.models as activities_models

import activities.activity_laps.models as activity_laps_models
import activities.activity_laps.schema as activity_laps_schema
import activities.activity_laps.utils as activity_laps_utils

import server_settings.crud as server_settings_crud

import core.logger as core_logger


def get_activity_laps(activity_id: int, db: Session):
    try:
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

        # Get the activity from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if the activity exists, if not return None
        if not activity:
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


def get_public_activity_laps(activity_id: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_crud.get_server_settings(db)

        # Return None if public sharable links are disabled
        if not server_settings or not server_settings.public_shareable_links:
            return None

        # Get the activity laps from the database
        activity_laps = (
            db.query(activity_laps_models.ActivityLaps)
            .join(
                activities_models.Activity,
                activities_models.Activity.id
                == activity_laps_models.ActivityLaps.activity_id,
            )
            .filter(
                activity_laps_models.ActivityLaps.activity_id == activity_id,
                activities_models.Activity.visibility == 0,
                activities_models.Activity.id == activity_id,
            )
            .all()
        )

        # Check if there are activity laps, if not return None
        if not activity_laps:
            return None

        # Get the activity from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if the activity exists, if not return None
        if not activity:
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
