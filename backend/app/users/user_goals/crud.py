from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime, timedelta

from activities.activity.utils import ACTIVITY_ID_TO_NAME

import users.user_goals.schema as user_goals_schema
import users.user_goals.models as user_goals_models

import activities.activity.models as activity_models

import core.logger as core_logger


def create_user_goal(db: Session, user_id: int, user_goal: user_goals_schema.UserGoalBase):
    """Create a new user goal"""
    try:

        existing_goals = (
            db.query(user_goals_models.UserGoal)
                .filter(user_goals_models.UserGoal.user_id == user_id)
                .filter(user_goals_models.UserGoal.activity_type == user_goal.activity_type)
                .filter(user_goals_models.UserGoal.interval == user_goal.interval)
                .all()
        )

        if existing_goals:
            # If there are existing goals for this user, activity type, and interval, raise an error
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has a goal for this activity type and interval."
            )
        
        db_user_goal = user_goals_models.UserGoal(
            user_id=user_id,
            activity_type=user_goal.activity_type,
            interval=user_goal.interval,
            goal_duration=user_goal.goal_duration,
            goal_distance=user_goal.goal_distance,
            goal_elevation=user_goal.goal_elevation,
            goal_calories=user_goal.goal_calories,
            goal_steps=user_goal.goal_steps,
            goal_count=user_goal.goal_count,
        )
        db.add(db_user_goal)
        db.commit()
        db.refresh(db_user_goal)
        return db_user_goal
    except HTTPException as http_err:
        raise http_err
    except IntegrityError as err:
        # Log the exception
        core_logger.print_to_log(f"Error in create_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 400 Bad Request status code
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid data provided",
        ) from err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in create_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_goals(db: Session, user_id: int) -> List[user_goals_models.UserGoal]:
    """Get all user goals for a specific user"""
    try:
        return (
            db.query(user_goals_models.UserGoal)
            .filter(user_goals_models.UserGoal.user_id == user_id)
            .all()
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_goals: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_user_goal(db: Session, user_id: int, goal_id: int) -> Optional[user_goals_models.UserGoal]:
    """Get a specific user goal by ID"""
    try:
        return (
            db.query(user_goals_models.UserGoal)
            .filter(
                user_goals_models.UserGoal.user_id == user_id,
                user_goals_models.UserGoal.id == goal_id
            )
            .first()
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def update_user_goal(db: Session, user_id: int, goal_id: int, user_goal: user_goals_schema.UserGoalBase):
    """Update a user goal"""
    try:
        db_user_goal = (
            db.query(user_goals_models.UserGoal)
            .filter(
                user_goals_models.UserGoal.user_id == user_id,
                user_goals_models.UserGoal.id == goal_id
            )
            .first()
        )
        
        if not db_user_goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User goal not found"
            )
        
        # Update only provided fields
        update_data = user_goal.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_user_goal, field, value)
        
        db.commit()
        db.refresh(db_user_goal)
        return db_user_goal
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in update_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
        


def delete_user_goal(db: Session, user_id: int, goal_id: int):
    """Delete a user goal"""
    try:
        db_user_goal = (
            db.query(user_goals_models.UserGoal)
            .filter(
                user_goals_models.UserGoal.user_id == user_id,
                user_goals_models.UserGoal.id == goal_id
            )
            .first()
        )
        
        if not db_user_goal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User goal not found"
            )
        
        db.delete(db_user_goal)
        db.commit()
        return {"message": "User goal deleted successfully"}
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in delete_user_goal: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def calculate_user_goals(db: Session, user_id: int, date: Optional[str] = datetime.now().strftime("%Y-%m-%d")) -> List[user_goals_schema.UserGoalProgress]:
    """Get user goals filtered by interval"""
    try:
        goals = (
            db.query(user_goals_models.UserGoal)
            .filter(
                user_goals_models.UserGoal.user_id == user_id,
            )
            .all()
        )

        if not goals:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No user goals found for the specified user"
            )
        
        return [
            calculate_goal_progress_by_activity_type(db, goal, date)
            for goal in goals
        ]
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        print(err)
        core_logger.print_to_log(f"Error in get_user_goals_by_interval: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
        
def calculate_goal_progress_by_activity_type(
    db: Session, goal: user_goals_models.UserGoal,
    date: str
) -> user_goals_schema.UserGoalProgress:
    """Calculate goal progress for a specific activity type"""
    try:
        activities = get_activities_by_interval(db, goal, date)
        start_date, end_date = get_start_end_date_by_interval(goal.interval, date)

        if not activities:
            return user_goals_schema.UserGoalProgress(
                goal_id=goal.id,
                activity_type=goal.activity_type,
                activity_type_name=ACTIVITY_ID_TO_NAME[goal.activity_type] if goal.activity_type else None,
                interval=goal.interval,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),

                goal_duration=goal.goal_duration,
                goal_distance=goal.goal_distance,
                goal_elevation=goal.goal_elevation,
                goal_calories=goal.goal_calories,
                goal_steps=goal.goal_steps,
                goal_count=goal.goal_count
            )

        total_duration = sum(activity.total_elapsed_time or 0 for activity in activities)
        total_distance = sum(activity.distance or 0 for activity in activities)
        total_elevation = sum(activity.elevation_gain or 0 for activity in activities)
        total_calories = sum(activity.calories or 0 for activity in activities)

        return user_goals_schema.UserGoalProgress(
            goal_id=goal.id,
            activity_type=goal.activity_type,
            activity_type_name=ACTIVITY_ID_TO_NAME[goal.activity_type] if goal.activity_type else None, 
            interval=goal.interval,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            
            total_actitivies=len(activities),
            total_duration=total_duration,
            total_distance=total_distance,
            total_elevation=total_elevation,
            total_calories=total_calories,

            goal_duration=goal.goal_duration,
            goal_distance=goal.goal_distance,
            goal_elevation=goal.goal_elevation,
            goal_calories=goal.goal_calories,
            goal_steps=goal.goal_steps,
            goal_count=goal.goal_count
        )

    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in calculate_goal_progress_by_activity_type: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err  
    
def get_activities_by_interval(
    db: Session, goal: user_goals_models.UserGoal, date: str
) -> List[activity_models.Activity]:
    """Get activities filtered by goal interval"""

    try:
        start_date, end_date = get_start_end_date_by_interval(goal.interval, date)

        return (
            db.query(activity_models.Activity)
            .filter(
                activity_models.Activity.user_id == goal.user_id,
                activity_models.Activity.activity_type == goal.activity_type,
                activity_models.Activity.start_time >= start_date,
                activity_models.Activity.start_time <= end_date,
            )
            .all()
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_activities_by_interval: {err}", "error", exc=err)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
    

def get_start_end_date_by_interval(
    interval: str, date: str
) -> tuple[datetime, datetime]:
    """Get start and end dates based on the interval"""
    date_obj = datetime.strptime(date, "%Y-%m-%d")
    
    if interval == "weekly":
        start_date = date_obj - timedelta(days=date_obj.weekday())  # Monday
        end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59) # Sunday
    elif interval == "monthly":
        start_date = date_obj.replace(day=1)
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(seconds=1)  # Last day of the month
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid interval specified"
        )
    
    return start_date, end_date