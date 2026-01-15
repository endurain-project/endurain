from datetime import date, datetime
from urllib.parse import unquote

import activities.activity.models as activities_models
import activities.activity.schema as activities_schema
import activities.activity.utils as activities_utils

import followers.models as followers_models

import core.logger as core_logger
import core.sanitization as core_sanitization

import notifications.utils as notifications_utils

import server_settings.utils as server_settings_utils

import websocket.manager as websocket_manager

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session, joinedload


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
        core_logger.print_to_log(
            f"Error in get_all_activities: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_activities_no_serialize(db: Session):
    try:
        # Get the activities from the database
        activities = db.query(activities_models.Activity).all()

        # Check if there are activities if not return None
        if not activities:
            return None

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_all_activities_no_serialize: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities(
    user_id: int,
    db: Session,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
) -> list[activities_schema.Activity] | None:
    try:
        # Base query
        query = db.query(activities_models.Activity).filter(
            activities_models.Activity.user_id == user_id
        )

        # Apply filters
        if activity_type:
            # add filter for activity type
            query = query.filter(
                activities_models.Activity.activity_type == activity_type
            )

        if start_date:
            # add filter for start date
            query = query.filter(
                func.date(activities_models.Activity.start_time) >= start_date
            )

        if end_date:
            # add filter for end date
            query = query.filter(
                func.date(activities_models.Activity.start_time) <= end_date
            )

        if name_search:
            # Decode and prepare search term
            search_term = unquote(name_search).replace("+", " ").lower()
            # Apply search across name, town, city, and country
            query = query.filter(
                or_(
                    func.lower(activities_models.Activity.name).like(
                        f"%{search_term}%"
                    ),
                    func.lower(activities_models.Activity.town).like(
                        f"%{search_term}%"
                    ),
                    func.lower(activities_models.Activity.city).like(
                        f"%{search_term}%"
                    ),
                    func.lower(activities_models.Activity.country).like(
                        f"%{search_term}%"
                    ),
                )
            )

        # Apply sorting
        query = query.order_by(desc(activities_models.Activity.start_time))

        # Get the activities from the database
        activities = query.all()

        # Check if there are activities if not return None
        if not activities:
            return None

        # Serialize all activities in one pass
        serialized_activities = []
        for activity in activities:
            serialized_activities.append(activities_utils.serialize_activity(activity))

            if activity.user_id != user_id:
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return serialized_activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities: {err}", "error", exc=err
        )
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
                activities_models.Activity.garminconnect_gear_id.isnot(None),
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

            if activity.user_id != user_id:
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_by_user_id_and_garminconnect_gear_set: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_with_pagination(
    user_id: int,
    db: Session,
    page_number: int = 1,
    num_records: int = 5,
    activity_type: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    name_search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    user_is_owner: bool = False,
) -> list[activities_schema.Activity] | None:
    try:
        # Mapping from frontend sort keys to database model fields
        SORT_MAP = {
            "type": activities_models.Activity.activity_type,
            "name": activities_models.Activity.name,
            "start_time": activities_models.Activity.start_time,
            "duration": activities_models.Activity.total_timer_time,
            "distance": activities_models.Activity.distance,
            "calories": activities_models.Activity.calories,
            "elevation": activities_models.Activity.elevation_gain,
            "pace": activities_models.Activity.pace,
            "average_hr": activities_models.Activity.average_hr,
        }

        # Base query
        query = db.query(activities_models.Activity).filter(
            activities_models.Activity.user_id == user_id,
        )

        # Apply filters
        if activity_type:
            # add filter for activity type
            query = query.filter(
                activities_models.Activity.activity_type == activity_type
            )

        if start_date:
            # add filter for start date
            query = query.filter(
                func.date(activities_models.Activity.start_time) >= start_date
            )

        if end_date:
            # add filter for end date
            query = query.filter(
                func.date(activities_models.Activity.start_time) <= end_date
            )

        if name_search:
            # Decode and prepare search term
            search_term = unquote(name_search).replace("+", " ").lower()
            # Apply search across name, town, city, and country
            query = query.filter(
                or_(
                    func.lower(activities_models.Activity.name).like(
                        f"%{search_term}%"
                    ),
                    func.lower(activities_models.Activity.town).like(
                        f"%{search_term}%"
                    ),
                    func.lower(activities_models.Activity.city).like(
                        f"%{search_term}%"
                    ),
                    func.lower(activities_models.Activity.country).like(
                        f"%{search_term}%"
                    ),
                )
            )

        # Apply sorting
        sort_ascending = sort_order and sort_order.lower() == "asc"

        if sort_by == "location":
            # Special handling for location: sort by country, then city, then town
            # Handle nulls by using COALESCE with a maximum value for DESC or minimum value for ASC
            if sort_ascending:
                query = query.order_by(
                    func.coalesce(activities_models.Activity.country, "").asc(),
                    func.coalesce(activities_models.Activity.city, "").asc(),
                    func.coalesce(activities_models.Activity.town, "").asc(),
                )
            else:
                query = query.order_by(
                    func.coalesce(activities_models.Activity.country, "").desc(),
                    func.coalesce(activities_models.Activity.city, "").desc(),
                    func.coalesce(activities_models.Activity.town, "").desc(),
                )
        else:
            # Standard sorting for other columns
            sort_column = SORT_MAP.get(sort_by, activities_models.Activity.start_time)

            # For numeric columns, use COALESCE with a very small/large number
            if sort_column in [
                activities_models.Activity.distance,
                activities_models.Activity.total_timer_time,
                activities_models.Activity.calories,
                activities_models.Activity.elevation_gain,
                activities_models.Activity.pace,
                activities_models.Activity.average_hr,
            ]:
                if sort_ascending:
                    query = query.order_by(func.coalesce(sort_column, -999999).asc())
                else:
                    query = query.order_by(func.coalesce(sort_column, -999999).desc())
            # For string/date columns
            else:
                if sort_ascending:
                    query = query.order_by(sort_column.asc())
                else:
                    query = query.order_by(sort_column.desc())

        # Apply pagination
        paginated_query = query.offset((page_number - 1) * num_records).limit(
            num_records
        )

        # Fetch activities
        activities = paginated_query.all()

        # Serialize activities
        serialized_activities = []
        if activities:
            for activity in activities:
                if not user_is_owner:
                    activity.private_notes = None
                    if activity.hide_start_time:
                        activity.start_time = None
                        activity.end_time = None
                    if activity.hide_location:
                        activity.city = None
                        activity.town = None
                        activity.country = None
                    if activity.hide_gear:
                        activity.gear_id = None
                        activity.strava_gear_id = None
                        activity.garminconnect_gear_id = None
                serialized_activities.append(
                    activities_utils.serialize_activity(activity)
                )

        # Return the activities
        return serialized_activities if serialized_activities else None

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_with_pagination: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_distinct_activity_types_for_user(user_id: int, db: Session):
    try:
        # Query distinct activity types (IDs) for the user
        type_ids = (
            db.query(activities_models.Activity.activity_type)
            .filter(activities_models.Activity.user_id == user_id)
            .distinct()
            .order_by(activities_models.Activity.activity_type)
            .all()
        )

        # Map type IDs to names, excluding None values
        return {
            type_id: activities_utils.ACTIVITY_ID_TO_NAME.get(type_id, "Unknown")
            for type_id, in type_ids
            if type_id is not None
        }
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_distinct_activity_types_for_user: {err}", "error", exc=err
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
    user_is_owner: bool = False,
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

            if not user_is_owner:
                activity.private_notes = None
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_per_timeframe: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_per_timeframe_and_activity_type(
    user_id: int,
    activity_type: int,
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.activity_type == activity_type,
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

            if not user_is_owner:
                activity.private_notes = None
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_per_timeframe_and_activity_type: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_per_timeframe_and_activity_types(
    user_id: int,
    activity_types: list[int],
    start: datetime,
    end: datetime,
    db: Session,
    user_is_owner: bool = False,
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.activity_type.in_(activity_types),
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

            if not user_is_owner:
                activity.private_notes = None
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_per_timeframe_and_activity_types: {err}",
            "error",
            exc=err,
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
                activities_models.Activity.is_hidden.is_(False),
                activities_models.Activity.strava_activity_id.is_(None),
            )
            .order_by(desc(activities_models.Activity.start_time))
        ).all()

        # Check if there are activities if not return None
        if not activities:
            return None

        for activity in activities:
            activity = activities_utils.serialize_activity(activity)
            activity.private_notes = None
            if activity.hide_start_time:
                activity.start_time = None
                activity.end_time = None
            if activity.hide_location:
                activity.city = None
                activity.town = None
                activity.country = None
            if activity.hide_gear:
                activity.gear_id = None
                activity.strava_gear_id = None
                activity.garminconnect_gear_id = None

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_following_activities_per_timeframe: {err}",
            "error",
            exc=err,
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
                followers_models.Follower,
                followers_models.Follower.following_id
                == activities_models.Activity.user_id,
            )
            .filter(
                and_(
                    followers_models.Follower.follower_id == user_id,
                    followers_models.Follower.is_accepted,
                ),
                activities_models.Activity.visibility.in_([0, 1]),
                activities_models.Activity.is_hidden.is_(False),
                activities_models.Activity.strava_activity_id.is_(None),
            )
            .order_by(desc(activities_models.Activity.start_time))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Iterate and format the dates
        for activity in activities:
            activity = activities_utils.serialize_activity(activity)
            activity.private_notes = None
            if activity.hide_start_time:
                activity.start_time = None
                activity.end_time = None
            if activity.hide_location:
                activity.city = None
                activity.town = None
                activity.country = None
            if activity.hide_gear:
                activity.gear_id = None
                activity.strava_gear_id = None
                activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_following_activities_with_pagination: {err}",
            "error",
            exc=err,
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
                followers_models.Follower,
                followers_models.Follower.following_id
                == activities_models.Activity.user_id,
            )
            .filter(
                and_(
                    followers_models.Follower.follower_id == user_id,
                    followers_models.Follower.is_accepted,
                ),
                activities_models.Activity.visibility.in_([0, 1]),
                activities_models.Activity.is_hidden.is_(False),
                activities_models.Activity.strava_activity_id.is_(None),
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
            f"Error in get_user_following_activities: {err}", "error", exc=err
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
            if activity.user_id != user_id:
                activity.private_notes = None
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_by_gear_id_and_user_id: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_activities_by_gear_id_and_user_id_with_pagination(
    user_id: int, gear_id: int, page_number: int, num_records: int, db: Session
):
    try:
        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.gear_id == gear_id,
            )
            .order_by(desc(activities_models.Activity.start_time))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Iterate and format the dates
        for activity in activities:
            activity = activities_utils.serialize_activity(activity)
            if activity.user_id != user_id:
                activity.private_notes = None
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_user_activities_by_gear_id_and_user_id_with_pagination: {err}",
            "error",
            exc=err,
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

        if activity.user_id != user_id:
            activity.private_notes = None
            if activity.hide_start_time:
                activity.start_time = None
                activity.end_time = None
            if activity.hide_location:
                activity.city = None
                activity.town = None
                activity.country = None
            if activity.hide_gear:
                activity.gear_id = None
                activity.strava_gear_id = None
                activity.garminconnect_gear_id = None

        # Return the activities
        return activity

    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_by_id_from_user_id_or_has_visibility: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_by_id_if_is_public(activity_id: int, db: Session):
    try:
        # Check if public sharable links are enabled in server settings
        server_settings = server_settings_utils.get_server_settings_or_404(db)

        # Return None if public sharable links are disabled
        if not server_settings.public_shareable_links:
            return None

        # Get the activities from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.visibility == 0,
                activities_models.Activity.id == activity_id,
            )
            .first()
        )

        # Check if there are activities if not return None
        if not activity:
            return None

        activity = activities_utils.serialize_activity(activity)

        activity.private_notes = None
        if activity.hide_start_time:
            activity.start_time = None
            activity.end_time = None
        if activity.hide_location:
            activity.city = None
            activity.town = None
            activity.country = None
        if activity.hide_gear:
            activity.gear_id = None
            activity.strava_gear_id = None
            activity.garminconnect_gear_id = None

        # Return the activities
        return activity
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activity_by_id_if_is_public: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_by_id(
    activity_id: int, db: Session
) -> activities_schema.Activity | None:
    try:
        # Get the activities from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
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
            f"Error in get_activity_by_id: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activity_by_start_time(
    start_time: str | datetime, user_id: int, db: Session
) -> activities_schema.Activity | None:
    try:
        if isinstance(start_time, str):
            start_time = datetime.strptime(start_time, "%Y-%m-%dT%H:%M:%S")
        # Get the activities from the database
        activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.start_time == start_time,
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
            f"Error in get_activity_by_start_time: {err}", "error", exc=err
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
            f"Error in get_activity_by_id_from_user_id: {err}", "error", exc=err
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
            f"Error in get_activity_by_strava_id_from_user_id: {err}", "error", exc=err
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
            f"Error in get_activity_by_garminconnect_id_from_user_id: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_activities_if_contains_name(name: str, user_id: int, db: Session):
    try:
        # Define a search term
        partial_name = unquote(name).replace("+", " ").lower()

        # Get the activities from the database
        activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                func.lower(activities_models.Activity.name).like(f"%{partial_name}%"),
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
            if activity.user_id != user_id:
                activity.private_notes = None
                if activity.hide_start_time:
                    activity.start_time = None
                    activity.end_time = None
                if activity.hide_location:
                    activity.city = None
                    activity.town = None
                    activity.country = None
                if activity.hide_gear:
                    activity.gear_id = None
                    activity.strava_gear_id = None
                    activity.garminconnect_gear_id = None

        # Return the activities
        return activities
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_activities_if_contains_name: {err}", "error", exc=err
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


async def create_activity(
    activity: activities_schema.Activity,
    websocket_manager: websocket_manager.WebSocketManager,
    db: Session,
    create_notification: bool = True,
) -> activities_schema.Activity:
    try:
        # Check if already is an activity created with the same start time
        activity_start_time_exists = get_activity_by_start_time(
            activity.start_time, activity.user_id, db
        )

        if activity_start_time_exists:
            activity.is_hidden = True

        # Create a new activity
        new_activity = activities_utils.transform_schema_activity_to_model_activity(
            activity
        )

        # Add the activity to the database
        db.add(new_activity)
        db.commit()
        db.refresh(new_activity)

        activity.id = new_activity.id
        activity.created_at = new_activity.created_at

        # Create a notification for the new activity
        if create_notification:
            if activity_start_time_exists:
                await notifications_utils.create_new_duplicate_start_time_activity_notification(
                    activity.user_id, new_activity.id, websocket_manager
                )
            else:
                await notifications_utils.create_new_activity_notification(
                    activity.user_id, new_activity.id, websocket_manager
                )

        # Return the activity
        return activity
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_activity: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_activity(
    user_id: int, activity_attributes: activities_schema.ActivityEdit, db: Session
):
    try:
        # Get the activity from the database
        db_activity = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
                activities_models.Activity.id == activity_attributes.id,
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
        if isinstance(activity_attributes, BaseModel):
            activity_data = activity_attributes.model_dump(exclude_unset=True)
        else:
            activity_data = {
                key: value
                for key, value in vars(activity_attributes).items()
                if value is not None
            }

        # Sanitize markdown fields to prevent XSS
        if "description" in activity_data:
            activity_data["description"] = core_sanitization.sanitize_markdown(
                activity_data["description"]
            )
        if "private_notes" in activity_data:
            activity_data["private_notes"] = core_sanitization.sanitize_markdown(
                activity_data["private_notes"]
            )

        # Iterate over the fields and update the db_activity dynamically
        for key, value in activity_data.items():
            setattr(db_activity, key, value)

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_activity: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_user_activities_visibility(user_id: int, visibility: int, db: Session):
    try:
        # Get the activity from the database
        db_activities = (
            db.query(activities_models.Activity)
            .filter(
                activities_models.Activity.user_id == user_id,
            )
            .all()
        )

        if db_activities is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User has no activities",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Iterate over the activities and update the visibility
        for db_activity in db_activities:
            db_activity.visibility = visibility

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in edit_user_activities_visibility: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_multiple_activities_gear_id(
    activities: list[activities_schema.Activity], user_id: int, db: Session
):
    try:
        if activities:
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
            f"Error in edit_multiple_activities_gear_id: {err}", "error", exc=err
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
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_activity: {err}", "error", exc=err)

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
            f"Error in delete_all_strava_activities_for_user: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
