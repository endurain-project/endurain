from pydantic import BaseModel, field_validator
from activities.activity.utils import ACTIVITY_ID_TO_NAME
from typing import Optional

allowed_intervals = ["daily", "weekly", "monthly"]
allowed_intervals_not_found_error = ValueError(f"Interval must be one of: {', '.join(allowed_intervals)}")
goal_value_error = ValueError("Goal values must be non-negative")

class UserGoalBase(BaseModel):
    interval: str
    activity_type: int
    goal_duration: Optional[int] = 0
    goal_distance: Optional[int] = 0
    goal_elevation: Optional[int] = 0
    goal_calories: Optional[int] = 0
    goal_steps: Optional[int] = 0
    goal_count: Optional[int] = 0

    @field_validator("interval")
    def validate_interval(cls, value):
        if value not in allowed_intervals:
            raise allowed_intervals_not_found_error
        return value

    @field_validator("goal_duration", "goal_distance", "goal_elevation", "goal_calories", "goal_steps", "goal_count")
    def validate_positive_values(cls, value):
        if value < 0:
            raise goal_value_error
        return value

    @field_validator("activity_type") 
    def activity_type_validation(cls, value):
        if value not in ACTIVITY_ID_TO_NAME:
            raise ValueError(f"Activity type must be one of: {', '.join(map(str, ACTIVITY_ID_TO_NAME.keys()))}")
        return value

class UserGoalProgress(BaseModel):
    goal_id: int
    activity_type: int
    activity_type_name: str
    interval: str
    start_date: str
    end_date: str
    #total
    total_actitivies: Optional[int] = 0
    total_duration: Optional[int] = 0
    total_distance: Optional[int] = 0
    total_elevation: Optional[int] = 0
    total_calories: Optional[int] = 0
    total_steps: Optional[int] = 0
    #goal
    goal_duration: Optional[int] = 0
    goal_distance: Optional[int] = 0
    goal_elevation: Optional[int] = 0
    goal_calories: Optional[int] = 0
    goal_steps: Optional[int] = 0
    goal_count: Optional[int] = 0

class UserGoal(UserGoalBase):
    id: int
    user_id: int

    class Config:
        orm_mode = True
