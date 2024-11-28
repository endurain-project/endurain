from operator import and_, or_
from fastapi import HTTPException, status
from datetime import datetime
from sqlalchemy import func, desc
from sqlalchemy.orm import Session, joinedload
from urllib.parse import unquote
from pydantic import BaseModel

import activities.models as activities_models
import activities.schema as activities_schema
import activities.utils as activities_utils

import core.logger as core_logger


def get_all_activities(db: Session):
    try:
        # Get the activities from the database
        activities = db.query(activities_models.Activity).all()

        # Check if there are activities if not return None
        if not activities:
            return None

        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_all_activities: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities(
    user_id: int,
    db: Session,
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(activities_models.Activity.user_id == user_id)
            .order_by(desc(activities_models.Activity.start_time))
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_activities: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_by_user_id_and_garminconnect_gear_set(
    user_id: int, db: Session
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.garminconnect_activity_id.isnot(None),
            )
            .order_by(desc(activities_models.Activity.start_time))
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Iterate and format the dates
        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_by_user_id_and_garminconnect_gear_set: {err}",
            "error",
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_with_pagination(
    user_id: int, db: Session, page_number: int = 1, num_records: int = 5
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(activities_models.Activity.user_id == user_id)
            .order_by(desc(activities_models.Activity.start_time))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_with_pagination: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_per_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    db: Session,
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                func.date(activities_models.Activity.start_time) >= start.date(),
                func.date(activities_models.Activity.start_time) <= end.date(),
            )
            .order_by(desc(activities_models.Activity.start_time))
        ).all()

        # Check if there are activities if not return None
        if not activities:
            return None

        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_per_timeframe: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_following_activities_per_timeframe(
    user_id: int,
    start: datetime,
    end: datetime,
    db: Session,
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                and_(
                    activities_models.Activity.user_id == user_id,
                    activities_models.Activity.visibility.in_([0, 1]),
                ),
                func.date(activities_models.Activity.start_time) >= start,
                func.date(activities_models.Activity.start_time) <= end,
            )
            .order_by(desc(activities_models.Activity.start_time))
        ).all()

        # Check if there are activities if not return None
        if not activities:
            return None

        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_following_activities_per_timeframe: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_following_activities_with_pagination(
    user_id: int, page_number: int, num_records: int, db: Session
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .join(
                activities_models.Follower,
                activities_models.Follower.following_id
                == activities_models.Activity.user_id,
            )
            .filter(
                and_(
                    activities_models.Follower.follower_id == user_id,
                    activities_models.Follower.is_accepted,
                ),
                activities_models.Activity.visibility.in_([0, 1]),
            )
            .order_by(desc(activities_models.Activity.start_time))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .options(joinedload(activities_models.Activity.user))
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Iterate and format the dates
        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_following_activities_with_pagination: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_following_activities(user_id, db):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .join(
                activities_models.Follower,
                activities_models.Follower.following_id
                == activities_models.Activity.user_id,
            )
            .filter(
                and_(
                    activities_models.Follower.follower_id == user_id,
                    activities_models.Follower.is_accepted,
                ),
                activities_models.Activity.visibility.in_([0, 1]),
            )
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Iterate and format the dates
        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_following_activities: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_by_gear_id_and_user_id(user_id: int, gear_id: int, db: Session):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.gear_id == gear_id,
            )
            .order_by(desc(activities_models.Activity.start_time))
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Iterate and format the dates
        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_by_gear_id_and_user_id: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_by_id_from_user_id_or_has_visibility(
    activity_id: int, user_id: int, db: Session
):
    try:
        # Get the activities from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                or_(
                    activities_models.Activity.user_id == user_id,
                    activities_models.Activity.visibility.in_([0, 1]),
                ),
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if there are activities if not return None
        if not activity:
            return None

        activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activity

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_by_id_from_user_id_or_has_visibility: {err}",
            "error",
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_by_id_from_user_id(
    activity_id: int, user_id: int, db: Session
) -> activities_schema.Activity:
    try:
        # Get the activities from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if there are activities if not return None
        if not activity:
            return None

        if not isinstance(activity.start_time, str):
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activity

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_by_id_from_user_id: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_by_strava_id_from_user_id(
    activity_strava_id: int, user_id: int, db: Session
):
    try:
        # Get the activities from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.strava_activity_id == activity_strava_id,
            )
            .first()
        )

        # Check if there are activities if not return None
        if not activity:
            return None

        activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activity

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_by_strava_id_from_user_id: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_by_garminconnect_id_from_user_id(
    activity_garminconnect_id: int, user_id: int, db: Session
):
    try:
        # Get the activities from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.garminconnect_activity_id
                == activity_garminconnect_id,
            )
            .first()
        )

        # Check if there are activities if not return None
        if not activity:
            return None

        activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activity

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_by_garminconnect_id_from_user_id: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activities_if_contains_name(name: str, user_id: int, db: Session):
    try:
        # Define a search term
        partial_name = unquote(name).replace("+", " ")

        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.name.like(f"%{partial_name}%"),
            )
            .order_by(desc(activities_models.Activity.start_time))
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Iterate and format the dates
        for activity in activities:
            activity = activities_utils.serialize_activity(activity)

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activities_if_contains_name: {err}", "error"
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_activity(activity: activities_schema.Activity, db: Session):
    try:
        # Create a new activity
        db_activity = activities_models.Activity(
            user_id=activity.user_id,
            distance=activity.distance,
            name=activity.name,
            activity_type=activity.activity_type,
            start_time=activity.start_time,
            end_time=activity.end_time,
            timezone=activity.timezone,
            total_elapsed_time=activity.total_elapsed_time,
            total_timer_time=activity.total_timer_time,
            city=activity.city,
            town=activity.town,
            country=activity.country,
            created_at=func.now(),
            elevation_gain=activity.elevation_gain,
            elevation_loss=activity.elevation_loss,
            pace=activity.pace,
            average_speed=activity.average_speed,
            max_speed=activity.max_speed,
            average_power=activity.average_power,
            max_power=activity.max_power,
            normalized_power=activity.normalized_power,
            average_hr=activity.average_hr,
            max_hr=activity.max_hr,
            average_cad=activity.average_cad,
            max_cad=activity.max_cad,
            workout_feeling=activity.workout_feeling,
            workout_rpe=activity.workout_rpe,
            calories=activity.calories,
            visibility=activity.visibility,
            gear_id=activity.gear_id,
            strava_gear_id=activity.strava_gear_id,
            strava_activity_id=activity.strava_activity_id,
            garminconnect_activity_id=activity.garminconnect_activity_id,
            garminconnect_gear_id=activity.garminconnect_gear_id,
        )

        # Add the activity to the database
        db.add(db_activity)
        db.commit()
        db.refresh(db_activity)

        activity.id = db_activity.id
        activity.created_at = db_activity.created_at

        # Return the activity
        return activity
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_activity: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_activity(user_id: int, activity: activities_schema.Activity, db: Session):
    try:
        # Get the activity from the database
        db_activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.id == activity.id,
            )
            .first()
        )

        if db_activity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Activity not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if 'activity' is a Pydantic model instance and convert it to a dictionary
        if isinstance(activity, BaseModel):
            activity_data = activity.dict(exclude_unset=True)
        else:
            activity_data = {
                key: value for key, value in vars(activity).items() if value is not None
            }

        # Iterate over the fields and update the db_activity dynamically
        for key, value in activity_data.items():
            setattr(db_activity, key, value)

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_activity: {err}", "error")

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def add_gear_to_activity(activity_id: int, gear_id: int, db: Session):
    try:
        # Get the activity from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(activities_models.Activity.id == activity_id)
            .first()
        )

        # Update the activity
        activity.gear_id = gear_id
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in add_gear_to_activity: {err}", "error")
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_multiple_activities_gear_id(
    activities: list[activities_schema.Activity], user_id: int, db: Session
):
    try:
        for activity in activities:
            # Get the activity from the database
            db_activity = get_activity_by_id_from_user_id(activity.id, user_id, db)

            # Update the activity
            db_activity.gear_id = activity.gear_id

        # Commit the transaction
        db.commit()

    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_multiple_activities_gear_id: {err}", "error"
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_activity(activity_id: int, db: Session):
    try:
        # Delete the activity
        num_deleted = (
            db.query(activities_models.Activity)
            .filter(activities_models.Activity.id == activity_id)
            .delete()
        )

        # Check if the activity was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Activity with id {activity_id} not found",
            )

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_activity: {err}", "error")

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_all_strava_activities_for_user(user_id: int, db: Session):
    try:
        # Delete the strava activities for the user
        num_deleted = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.strava_activity_id.isnot(None),
            )
            .delete()
        )

        # Check if activities were found and deleted and commit the transaction
        if num_deleted != 0:
            # Commit the transaction
            db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_all_strava_activities_for_user: {err}", "error"
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
