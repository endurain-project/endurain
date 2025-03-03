from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.models as activities_models

import activity_splits.schema as activity_splits_schema
import activity_splits.models as activity_splits_models

import server_settings.crud as server_settings_crud

import core.logger as core_logger


def get_activity_splits(activity_id: int, db: Session):
    try:
        # Get the activity splits from the database
        activity_splits = (
            db.query(activity_splits_models.ActivitySplits)
            .filter(
                activity_splits_models.ActivitySplits.activity_id == activity_id,
            )
            .all()
        )

        # Check if there are activity splits if not return None
        if not activity_splits:
            return None

        # Return the activity splits
        return activity_splits
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_splits: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_splits(activity_id: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_crud.get_server_settings(db)

        # Return None if public sharable links are disabled
        if not server_settings or not server_settings.public_shareable_links:
            return None
        
        # Get the activity splits from the database
        activity_splits = (
            db.query(activity_splits_models.ActivitySplits)
            .join(
                activities_models.Activity,
                activities_models.Activity.id
                == activity_splits_models.ActivitySplits.activity_id,
            )
            .filter(
                activity_splits_models.ActivitySplits.activity_id == activity_id,
                activities_models.Activity.visibility == 0,
                activities_models.Activity.id
                == activity_id,
            )
            .all()
        )

        # Check if there are activity splits, if not return None
        if not activity_splits:
            return None

        # Return the activity splits
        return activity_splits
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_public_activity_splits: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    

def create_activity_splits(activity_splits: list[activity_splits_schema.ActivitySplits], db: Session):
    try:
        # Create a list to store the ActivitySplits objects
        splits = []

        # Iterate over the list of ActivitySplits objects
        for split in activity_splits:
            # Create an ActivitySplits object
            db_stream = activity_splits_models.ActivitySplits(
                activity_id=split.activity_id,
                split_type=split.split_type,
                total_elapsed_time=split.total_elapsed_time,
                total_timer_time=split.total_timer_time,
                total_distance=split.total_distance,
                average_speed=split.avg_speed,
                start_time=split.start_time,
                total_ascent=split.total_ascent,
                total_descent=split.total_descent,
                start_position_lat=split.start_position_lat,
                start_position_long=split.start_position_long,
                end_position_lat=split.end_position_lat,
                end_position_long=split.end_position_long,
                max_speed=split.max_speed,
                end_time=split.end_time,
                total_calories=split.total_calories,
                start_elevation=split.start_elevation,
            )

            # Append the object to the list
            splits.append(db_stream)

        # Bulk insert the list of ActivitySplits objects
        db.bulk_save_objects(splits)
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger(f"Error in create_activity_splits: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
