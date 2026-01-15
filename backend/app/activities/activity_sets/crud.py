from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import activities.activity.schema as activities_schema
import activities.activity.models as activity_models
import activities.activity.crud as activity_crud

import activities.activity_sets.models as activity_sets_models
import activities.activity_sets.utils as activity_sets_utils

import server_settings.utils as server_settings_utils

import core.logger as core_logger


def get_activity_sets(activity_id: int, token_user_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        user_is_owner = True
        if token_user_id != activity.user_id:
            user_is_owner = False

        if not user_is_owner and activity.hide_workout_sets_steps:
            # If the user is not the owner and sets/steps are hidden, return None
            return None

        # Get the activity sets from the database
        activity_sets = (
            db.query(activity_sets_models.ActivitySets)
            .filter(
                activity_sets_models.ActivitySets.activity_id == activity_id,
            )
            .all()
        )

        # Check if there are activity sets if not return None
        if not activity_sets:
            return None

        # Serialize the activity sets
        for activity_set in activity_sets:
            activity_set = activity_sets_utils.serialize_activity_set(
                activity, activity_set
            )

        # Return the activity sets
        return activity_sets
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_activity_sets: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activities_sets(
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

        # Filter out hidden sets for activities the user doesn't own
        allowed_ids = [
            activity.id for activity in activities if activity.user_id == token_user_id
        ]

        if not allowed_ids:
            return []

        # Fetch all sets for allowed activities
        activity_sets = (
            db.query(activity_sets_models.ActivitySets)
            .filter(activity_sets_models.ActivitySets.activity_id.in_(allowed_ids))
            .all()
        )

        if not activity_sets:
            return []

        # Serialize each set
        serialized_sets = [
            activity_sets_utils.serialize_activity_set(
                activity_map[aset.activity_id], aset
            )
            for aset in activity_sets
        ]

        return serialized_sets

    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_activities_sets: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_public_activity_sets(activity_id: int, db: Session):
    try:
        activity = activity_crud.get_activity_by_id(activity_id, db)

        if not activity:
            # If the activity does not exist, return None
            return None

        if activity.hide_workout_sets_steps:
            # If the sets/steps are hidden, return None
            return None

        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links:
            return None

        # Get the activity sets from the database
        activity_sets = (
            db.query(activity_sets_models.ActivitySets)
            .join(
                activity_models.Activity,
                activity_models.Activity.id
                == activity_sets_models.ActivitySets.activity_id,
            )
            .filter(
                activity_sets_models.ActivitySets.activity_id == activity_id,
                activity_models.Activity.visibility == 0,
                activity_models.Activity.id == activity_id,
            )
            .all()
        )

        # Check if there are activity sets, if not return None
        if not activity_sets:
            return None

        # Serialize the activity sets
        for set in activity_sets:
            set = activity_sets_utils.serialize_activity_set(activity, set)

        # Return the activity sets
        return activity_sets
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_public_activity_sets: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity_sets(
    activity_sets: list,
    activity_id: int,
    db: Session,
):
    try:
        # Create a list to store the ActivitySets objects
        sets = []

        # Iterate over the list of ActivitySets objects
        for activity_set in activity_sets:
            # Check if it's a Pydantic model (has attributes instead of being subscriptable)
            if hasattr(activity_set, "__fields__"):
                duration = activity_set.duration
                repetitions = activity_set.repetitions
                weight = activity_set.weight
                set_type = activity_set.set_type
                start_time = activity_set.start_time
                category = activity_set.category if activity_set.category else None
                category_subtype = (
                    activity_set.category_subtype
                    if activity_set.category_subtype
                    else None
                )
            else:
                duration = activity_set[0]
                repetitions = activity_set[1]
                weight = activity_set[2]
                set_type = activity_set[3]
                start_time = activity_set[4]
                # Handle category - check if it's a tuple
                if activity_set[5] is not None:
                    if isinstance(activity_set[5], tuple):
                        category = (
                            activity_set[5][0]
                            if activity_set[5][0] is not None
                            else None
                        )
                    else:
                        category = activity_set[5]
                else:
                    category = None
                # Handle category_subtype - check if it's a tuple
                if activity_set[6] is not None:
                    if isinstance(activity_set[6], tuple):
                        category_subtype = (
                            activity_set[6][0]
                            if activity_set[6][0] is not None
                            else None
                        )
                    else:
                        category_subtype = activity_set[6]
                else:
                    category_subtype = None

            # Create a new ActivitySets object
            db_activity_set = activity_sets_models.ActivitySets(
                activity_id=activity_id,
                duration=duration,
                repetitions=repetitions,
                weight=weight,
                set_type=set_type,
                start_time=start_time,
                category=category,
                category_subtype=category_subtype,
            )

            # Append the object to the list
            sets.append(db_activity_set)

        # Bulk insert the list of ActivitySets objects
        db.bulk_save_objects(sets)
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in create_activity_sets: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
