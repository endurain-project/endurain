from pydantic import BaseModel, field_validator
from activities.activity.utils import ACTIVITY_ID_TO_NAME

allowed_intervals = ["daily", "weekly", "monthly", "yearly"]
allowed_intervals_not_found_error = ValueError(
    f"Interval must be one of: {', '.join(allowed_intervals)}"
)
allowed_activity_types_not_found_error = ValueError(
    "Activity type must be between 1 and 5"
)
allowed_goal_types_not_found_error = ValueError("Goal type must be between 1 and 6")
goal_value_error = ValueError("Goal values must be non-negative")


class UserGoalBase(BaseModel):
    interval: str
    activity_type: int
    goal_type: int
    goal_calories: int | None
    goal_activities_number: int | None
    goal_distance: int | None
    goal_elevation: int | None
    goal_duration: int | None
    goal_steps: int | None

    @field_validator("interval")
    def validate_interval(cls, value):
        if value not in allowed_intervals:
            raise allowed_intervals_not_found_error
        return value

    @field_validator("activity_type")
    def validate_activity_type(cls, value):
        if value < 1 or value > 5:
            raise allowed_activity_types_not_found_error
        return value

    @field_validator("goal_type")
    def validate_goal_type(cls, value):
        if value < 1 or value > 6:
            raise allowed_goal_types_not_found_error
        return value

    @field_validator(
        "goal_calories",
        "goal_activities_number",
        "goal_distance",
        "goal_elevation",
        "goal_duration",
        "goal_steps",
    )
    def validate_positive_values(cls, value):
        if value is not None and value < 0:
            raise goal_value_error
        return value


class UserGoalProgress(BaseModel):
    goal_id: int
    activity_type: int
    activity_type_name: str
    interval: str
    start_date: str
    end_date: str
    # total
    total_activities: int | None = 0
    total_duration: int | None = 0
    total_distance: int | None = 0
    total_elevation: int | None = 0
    total_calories: int | None = 0
    total_steps: int | None = 0
    # goal
    goal_duration: int | None = 0
    goal_distance: int | None = 0
    goal_elevation: int | None = 0
    goal_calories: int | None = 0
    goal_steps: int | None = 0
    goal_count: int | None = 0


class UserGoal(UserGoalBase):
    id: int
    user_id: int

    model_config = {"from_attributes": True}
