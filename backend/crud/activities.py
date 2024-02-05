import logging

from operator import and_, or_
from fastapi import HTTPException, status
from datetime import datetime
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from schemas import activities as activities_schemas
import models

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_user_activities(
    user_id: int,
    db: Session,
):
    try:
        # Get the activities from the database
        activities = (
            db.query(models.Activity)
            .filter(models.Activity.user_id == user_id)
            .order_by(desc(models.Activity.start_time))
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_user_activities: {err}", exc_info=True)
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
            db.query(models.Activity)
            .filter(models.Activity.user_id == user_id)
            .order_by(desc(models.Activity.start_time))
            .offset((page_number - 1) * num_records)
            .limit(num_records)
            .all()
        )

        # Check if there are activities if not return None
        if not activities:
            return None

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_user_activities_with_pagination: {err}", exc_info=True)
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
    """Get the activities of a user for a given week"""
    try:
        # Get the activities from the database
        activities = (
            db.query(models.Activity)
            .filter(
                models.Activity.user_id == user_id,
                func.date(models.Activity.start_time) >= start,
                func.date(models.Activity.start_time) <= end,
            )
            .order_by(desc(models.Activity.start_time))
        ).all()

        # Check if there are activities if not return None
        if not activities:
            return None

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_user_activities_per_timeframe: {err}", exc_info=True)
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
    """Get the activities of the users that the user is following for a given week"""
    try:
        # Get the activities from the database
        activities = (
            db.query(models.Activity)
            .filter(
                and_(
                    models.Activity.user_id == user_id,
                    models.Activity.visibility.in_([0, 1]),
                ),
                func.date(models.Activity.start_time) >= start,
                func.date(models.Activity.start_time) <= end,
            )
            .order_by(desc(models.Activity.start_time))
        ).all()

        # Check if there are activities if not return None
        if not activities:
            return None

        # Return the activities
        return activities

    except Exception as err:
        # Log the exception
        logger.error(
            f"Error in get_user_following_activities_per_timeframe: {err}", exc_info=True
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
