from enum import Enum, IntEnum
from typing import Annotated
from pydantic import (
    BaseModel,
    model_validator,
    ConfigDict,
    StrictInt,
    Field,
)
from pydantic_core import PydanticCustomError


class Interval(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    yearly = "yearly"


class ActivityType(IntEnum):
    run = 1
    bike = 2
    swim = 3
    walk = 4
    strength = 5


class GoalType(IntEnum):
    calories = 1
    activities = 2
    distance = 3
    elevation = 4
    duration = 5
    steps = 6


# goal_type -> field name
TYPE_TO_FIELD = {
    GoalType.calories: "goal_calories",
    GoalType.activities: "goal_activities_number",
    GoalType.distance: "goal_distance",
    GoalType.elevation: "goal_elevation",
    GoalType.duration: "goal_duration",
    GoalType.steps: "goal_steps",
}

# Non-negative int helper; attach constraint at the field level
NonNegInt = Annotated[int, Field(ge=0)]


class UserGoalBase(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    interval: Interval
    activity_type: ActivityType
    goal_type: GoalType

    goal_calories: NonNegInt | None = None
    goal_activities_number: NonNegInt | None = None
    goal_distance: NonNegInt | None = None
    goal_elevation: NonNegInt | None = None
    goal_duration: NonNegInt | None = None
    goal_steps: NonNegInt | None = None

    @model_validator(mode="after")
    def ensure_correct_goal_field(self):
        required_field = TYPE_TO_FIELD.get(self.goal_type)
        if required_field is None:
            return self

        if getattr(self, required_field) is None:
            raise PydanticCustomError(
                "missing_goal_value",
                f"{required_field} is required when goal_type={self.goal_type.name}",
            )

        for name in TYPE_TO_FIELD.values():
            if name != required_field and getattr(self, name) is not None:
                raise PydanticCustomError(
                    "exclusive_goal_value",
                    f"Only {required_field} may be set when goal_type={self.goal_type.name}",
                )
        return self


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
    id: StrictInt
    user_id: StrictInt
    model_config = ConfigDict(from_attributes=True, extra="forbid")
