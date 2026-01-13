"""User goals Pydantic schemas and validators."""

from enum import Enum, IntEnum
from typing import Annotated
from pydantic import (
    BaseModel,
    model_validator,
    ConfigDict,
    StrictInt,
    StrictStr,
    Field,
)
from pydantic_core import PydanticCustomError


class Interval(str, Enum):
    """
    Recurrence intervals for user goals.

    Attributes:
        DAILY: Daily recurrence interval.
        WEEKLY: Weekly recurrence interval.
        MONTHLY: Monthly recurrence interval.
        YEARLY: Yearly recurrence interval.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ActivityType(IntEnum):
    """
    Supported activity types for user goals.

    Attributes:
        RUN: Running activities.
        BIKE: Cycling activities.
        SWIM: Swimming activities.
        WALK: Walking or hiking activities.
        STRENGTH: Strength or resistance training.
        CARDIO: Cardiovascular training.
    """

    RUN = 1
    BIKE = 2
    SWIM = 3
    WALK = 4
    STRENGTH = 5
    CARDIO = 6


class GoalType(IntEnum):
    """
    Types of measurable user goals.

    Attributes:
        CALORIES: Target calories burned.
        ACTIVITIES: Target count of completed activities.
        DISTANCE: Target distance traveled.
        ELEVATION: Target elevation gain.
        DURATION: Target total duration.
    """

    CALORIES = 1
    ACTIVITIES = 2
    DISTANCE = 3
    ELEVATION = 4
    DURATION = 5


# goal_type -> field name
TYPE_TO_FIELD = {
    GoalType.CALORIES: "goal_calories",
    GoalType.ACTIVITIES: "goal_activities_number",
    GoalType.DISTANCE: "goal_distance",
    GoalType.ELEVATION: "goal_elevation",
    GoalType.DURATION: "goal_duration",
}


class UserGoalBase(BaseModel):
    """
    Base schema for user fitness goals.

    Attributes:
        interval: Goal time interval (daily, weekly, monthly,
            yearly).
        activity_type: Type of activity for the goal.
        goal_type: Type of goal metric being tracked.
        goal_calories: Target calories in kcal.
        goal_activities_number: Target number of activities.
        goal_distance: Target distance in meters.
        goal_elevation: Target elevation gain in meters.
        goal_duration: Target duration in seconds.
    """

    interval: Interval = Field(..., description="Goal time interval")
    activity_type: ActivityType = Field(
        ..., description="Type of activity for the goal"
    )
    goal_type: GoalType = Field(..., description="Type of goal metric being tracked")
    goal_calories: StrictInt | None = Field(
        None, ge=0, description="Target calories in kcal"
    )
    goal_activities_number: StrictInt | None = Field(
        None, ge=0, description="Target number of activities"
    )
    goal_distance: StrictInt | None = Field(
        None, ge=0, description="Target distance in meters"
    )
    goal_elevation: StrictInt | None = Field(
        None, ge=0, description="Target elevation gain in meters"
    )
    goal_duration: StrictInt | None = Field(
        None, ge=0, description="Target duration in seconds"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )

    @model_validator(mode="after")
    def ensure_correct_goal_field(self):
        """
        Validate exactly one goal field matches goal_type.

        Returns:
            Self with validated goal field.

        Raises:
            PydanticCustomError: If required field missing or
                extra fields set.
        """
        # Handle both enum instance and integer value
        goal_type_value = (
            self.goal_type if isinstance(self.goal_type, int) else self.goal_type.value
        )
        goal_type_name = (
            GoalType(goal_type_value).name
            if isinstance(self.goal_type, int)
            else self.goal_type.name
        )

        required_field = TYPE_TO_FIELD.get(goal_type_value)
        if required_field is None:
            return self

        if getattr(self, required_field) is None:
            raise PydanticCustomError(
                "missing_goal_value",
                "{field} is required when goal_type={goal_type}",
                {
                    "field": required_field,
                    "goal_type": goal_type_name,
                },
            )

        for name in TYPE_TO_FIELD.values():
            if name != required_field and getattr(self, name) is not None:
                raise PydanticCustomError(
                    "exclusive_goal_value",
                    "Only {field} may be set when goal_type={goal_type}",
                    {
                        "field": required_field,
                        "goal_type": goal_type_name,
                    },
                )
        return self


class UserGoalCreate(UserGoalBase):
    """
    Schema for creating a new user goal.

    Inherits all validation from UserGoalBase.
    """


class UserGoalEdit(UserGoalBase):
    """
    Schema for updating an existing user goal.

    Supports partial updates. Omitted fields remain unchanged.
    """


class UserGoalRead(UserGoalBase):
    """
    Schema for reading a user goal.

    Attributes:
        id: Unique identifier for the goal.
        user_id: User who owns this goal.
    """

    id: StrictInt = Field(..., description="Unique identifier for the goal")
    user_id: StrictInt = Field(..., description="User who owns this goal")


class UserGoalProgress(BaseModel):
    """
    Schema for user goal progress tracking.

    Attributes:
        goal_id: Goal identifier.
        interval: Goal time interval.
        activity_type: Activity type for this goal.
        goal_type: Type of goal metric.
        start_date: Period start date.
        end_date: Period end date.
        percentage_completed: Completion percentage.
        total_calories: Total calories achieved.
        total_activities_number: Total activities completed.
        total_distance: Total distance achieved.
        total_elevation: Total elevation gained.
        total_duration: Total duration achieved.
        goal_calories: Target calories.
        goal_activities_number: Target activities count.
        goal_distance: Target distance.
        goal_elevation: Target elevation.
        goal_duration: Target duration.
    """

    goal_id: StrictInt = Field(..., ge=0, description="Goal identifier")
    interval: Interval = Field(..., description="Goal time interval")
    activity_type: ActivityType = Field(..., description="Activity type for this goal")
    goal_type: GoalType
    start_date: StrictStr = Field(..., description="Period start date")
    end_date: StrictStr = Field(..., description="Period end date")
    percentage_completed: StrictInt | None = Field(
        None, ge=0, le=100, description="Completion percentage"
    )
    # total
    total_calories: StrictInt | None = Field(
        None, ge=0, description="Total calories achieved"
    )
    total_activities_number: StrictInt | None = Field(
        None, ge=0, description="Total activities completed"
    )
    total_distance: StrictInt | None = Field(
        None, ge=0, description="Total distance achieved"
    )
    total_elevation: StrictInt | None = Field(
        None, ge=0, description="Total elevation gained"
    )
    total_duration: StrictInt | None = Field(
        None, ge=0, description="Total duration achieved"
    )
    # goal
    goal_calories: StrictInt | None = Field(None, ge=0, description="Target calories")
    goal_activities_number: StrictInt | None = Field(
        None, ge=0, description="Target activities count"
    )
    goal_distance: StrictInt | None = Field(None, ge=0, description="Target distance")
    goal_elevation: StrictInt | None = Field(None, ge=0, description="Target elevation")
    goal_duration: StrictInt | None = Field(None, ge=0, description="Target duration")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )
