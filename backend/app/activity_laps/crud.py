from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.models as activities_models

import activity_laps.models as activity_laps_models
import activity_laps.schema as activity_laps_schema

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

        # Return the activity laps
        return activity_laps
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_laps: {err}", "error", exc=err
        )
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
                activities_models.Activity.id
                == activity_id,
            )
            .all()
        )

        # Check if there are activity laps, if not return None
        if not activity_laps:
            return None

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
    

def create_activity_laps(activity_laps: list[activity_laps_schema.ActivityLaps], activity_id: int, db: Session):
    try:
        # Create a list to store the ActivityLaps objects
        laps = []

        # Iterate over the list of ActivityLaps objects
        for lap in activity_laps:
            # Create an ActivitySplits object
            db_stream = activity_laps_models.ActivityLaps(
                activity_id=activity_id,
                start_time=lap["start_time"],
                start_position_lat=lap["start_position_lat"],
                start_position_long=lap["start_position_long"],
                end_position_lat=lap["end_position_lat"],
                end_position_long=lap["end_position_long"],
                total_elapsed_time=lap["total_elapsed_time"],
                total_timer_time=lap["total_timer_time"],
                total_distance=lap["total_distance"],
                total_cycles=lap["total_cycles"],
                total_calories=lap["total_calories"],
                avg_heart_rate=lap["avg_heart_rate"],
                max_heart_rate=lap["max_heart_rate"],
                avg_cadence=lap["avg_cadence"],
                max_cadence=lap["max_cadence"],
                avg_power=lap["avg_power"],
                max_power=lap["max_power"],
                total_ascent=lap["total_ascent"],
                total_descent=lap["total_descent"],
                intensity=lap["intensity"],
                lap_trigger=lap["lap_trigger"],
                sport = lap["sport"],
                sub_sport = lap["sub_sport"],
                normalized_power = lap["normalized_power"],
                total_work = lap["total_work"],
                avg_vertical_oscillation = lap["avg_vertical_oscillation"],
                avg_stance_time = lap["avg_stance_time"],
                avg_fractional_cadence = lap["avg_fractional_cadence"],
                max_fractional_cadence = lap["max_fractional_cadence"],
                enhanced_avg_speed = lap["enhanced_avg_speed"],
                enhanced_max_speed = lap["enhanced_max_speed"],
                enhanced_min_altitude = lap["enhanced_min_altitude"],
                enhanced_max_altitude = lap["enhanced_max_altitude"],
                avg_vertical_ratio = lap["avg_vertical_ratio"],
                avg_step_length = lap["avg_step_length"],
            )

            # Append the object to the list
            laps.append(db_stream)

        # Bulk insert the list of ActivitySplits objects
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
