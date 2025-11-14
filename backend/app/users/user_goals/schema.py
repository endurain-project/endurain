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
    """Enumeration of recurrence intervals for user goals.

    Members:
        DAILY (str): "daily" — Recurs every calendar day.
        WEEKLY (str): "weekly" — Recurs every calendar week.
        MONTHLY (str): "monthly" — Recurs every calendar month.
        YEARLY (str): "yearly" — Recurs every calendar year.

    This enum subclasses str and Enum so members behave like strings (e.g. Interval.DAILY.value == "daily")
    and can be used directly where string values are required (e.g. JSON serialization).

    Example:
        Interval.DAILY
        Interval.DAILY.value  # 'daily'
        if interval == Interval.WEEKLY:
            ...
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ActivityType(IntEnum):
    """IntEnum representing the supported activity types.

    This enumeration defines the canonical set of activity categories used to
    classify user activities and goals in the application. Being an IntEnum,
    members are integer-backed and can be compared to integers and stored in
    integer-based fields (e.g., database columns).

    Members:
        RUN (1): Running activities.
        BIKE (2): Cycling activities.
        SWIM (3): Swimming activities.
        WALK (4): Walking or hiking activities.
        STRENGTH (5): Strength or resistance training sessions.
        CARDIO (6): Cardiovascular training activities.
    """

    RUN = 1
    BIKE = 2
    SWIM = 3
    WALK = 4
    STRENGTH = 5
    CARDIO = 6


class GoalType(IntEnum):
    """
    An IntEnum describing the types of user goals supported by the application.

    Each member corresponds to a category of measurable user goal and has a fixed
    integer value intended for stable storage and interchange (e.g., database
    fields or compact API payloads).

    Members
    -------
    calories (1)
        Target amount of calories burned.
    activities (2)
        Target count of completed activities (e.g., workouts).
    distance (3)
        Target distance traveled (units configured elsewhere, e.g., meters or kilometers).
    elevation (4)
        Target elevation gain (units configured elsewhere, e.g., meters).
    duration (5)
        Target total duration (typically represented in seconds).

    Notes
    -----
    - As an IntEnum, members behave like both enum values and integers: comparisons
      with ints are supported and the numeric values are suitable for persisted
      representations.
    - The numeric values are part of the external representation; avoid renumbering
      them to prevent compatibility and migration issues.

    Examples
    --------
    >>> GoalType.distance
    GoalType.distance
    >>> GoalType.distance.value
    3
    >>> GoalType(3) is GoalType.distance
    True
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

# Non-negative int helper; attach constraint at the field level
NonNegInt = Annotated[int, Field(ge=0)]


class UserGoalBase(BaseModel):
    """Pydantic model representing a user's periodic fitness goal.

    This model groups the target information for a specific activity and goal type
    over a defined time interval. Exactly one of the numeric goal_* fields must be
    set according to the mapping TYPE_TO_FIELD which maps a GoalType to the
    corresponding attribute name (for example, GoalType.DISTANCE -> "goal_distance").

    Attributes
    ----------
    interval : Interval
        The time interval the goal applies to (e.g. DAILY, WEEKLY).
    activity_type : ActivityType
        The activity to which the goal applies (e.g. RUNNING, CYCLING).
    goal_type : GoalType
        Determines which specific goal_xxx field is required.
    goal_calories : NonNegInt | None
        Target calories (non-negative integer) or None.
    goal_activities_number : NonNegInt | None
        Target number of activities or None.
    goal_distance : NonNegInt | None
        Target distance (units handled elsewhere) or None.
    goal_elevation : NonNegInt | None
        Target elevation gain or None.
    goal_duration : NonNegInt | None
        Target duration in seconds or None.

    Validation behavior
    -------------------
    - A post-validation hook (ensure_correct_goal_field) consults TYPE_TO_FIELD to
      determine which goal_* attribute is required for the selected goal_type.
    - If TYPE_TO_FIELD has no entry for the provided goal_type, no exclusive-field
      enforcement is performed.
    - If the mapped attribute is None, a PydanticCustomError with code
      "missing_goal_value" is raised.
    - If any other goal_* attribute is set in addition to the required one, a
      PydanticCustomError with code "exclusive_goal_value" is raised.
    - The model config enforces:
      - from_attributes=True (allow construction from objects/attributes),
      - extra="forbid" (reject unknown fields),
      - validate_assignment=True (run validators on attribute assignment).

    Examples
    --------
    Valid:
        UserGoalBase(
            interval=Interval.WEEK,
            activity_type=ActivityType.RUNNING,
            goal_type=GoalType.DISTANCE,
            goal_distance=10000,

    Invalid (missing required value):
        UserGoalBase(
            interval=Interval.WEEK,
            activity_type=ActivityType.RUNNING,
            goal_type=GoalType.DISTANCE,
        # raises PydanticCustomError(code="missing_goal_value")

    Invalid (more than one goal field set):
        UserGoalBase(
            interval=Interval.WEEK,
            activity_type=ActivityType.RUNNING,
            goal_type=GoalType.DISTANCE,
            goal_distance=10000,
            goal_duration=3600,
        # raises PydanticCustomError(code="exclusive_goal_value")
    """

    interval: Interval
    activity_type: ActivityType
    goal_type: GoalType
    goal_calories: NonNegInt | None = None
    goal_activities_number: NonNegInt | None = None
    goal_distance: NonNegInt | None = None
    goal_elevation: NonNegInt | None = None
    goal_duration: NonNegInt | None = None

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )

    @model_validator(mode="after")
    def ensure_correct_goal_field(self):
        """
        Validate that exactly the field associated with the current goal_type is set.

        Uses the global TYPE_TO_FIELD mapping to determine which attribute name is
        required for self.goal_type. Behavior:
        - If TYPE_TO_FIELD.get(self.goal_type) is None, no requirement exists and the
            method returns self unchanged.
        - Otherwise:
            - If the required attribute is None, raises PydanticCustomError with code
                "missing_goal_value" and a message indicating which field is required for the
                current goal_type.
            - If any other attribute listed in TYPE_TO_FIELD.values() is set (not None),
                raises PydanticCustomError with code "exclusive_goal_value" and a message
                stating that only the required field may be set for the current goal_type.
        - If the checks pass, returns self to allow validator chaining.

        Assumes self has an attribute goal_type (often an Enum with a .name) and
        attributes named by the values in TYPE_TO_FIELD.

        Raises:
                PydanticCustomError: "missing_goal_value" when the required field is missing.
                PydanticCustomError: "exclusive_goal_value" when a non-required field is set.

        Returns:
                self: the validated instance (unchanged).
        """
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


class UserGoalCreate(UserGoalBase):
    """Schema for creating a new UserGoal.

    This model is intended for use when deserializing and validating incoming
    data to create a new user goal. It inherits fields and any common
    validation from UserGoalBase and exposes only the properties that a
    client is allowed to supply when creating a goal.

    Notes:
    - Server-managed/read-only fields (for example: `id`, `created_at`,
        `updated_at`, or other computed attributes) should not be included
        here and will be set by the application when persisting the resource.
    - Additional business-rule validation (e.g. start_date <= end_date,
        positive target values) may be enforced on the model or in service
        layer logic.

    Usage:
            Use this schema as the request body type for endpoints that create
            user goals. Instantiate it with validated input (e.g. UserGoalCreate(**payload))
            before passing the data to persistence logic.

    Example:
            payload = {
                    "title": "Run 100 km",
                    "target_value": 100,
                    "unit": "km",
                    "start_date": "2025-01-01",
                    "end_date": "2025-03-31",
            }
            goal_in = UserGoalCreate(**payload)
    """


class UserGoalEdit(UserGoalBase):
    """
    Schema for updating an existing user goal.

    Inherits from UserGoalBase and is intended for partial-update operations
    (e.g., PATCH). Fields defined on the base schema are treated as optional
    when used with this model; only the attributes supplied in an update payload
    will be applied to the stored goal. Any validation rules declared on the
    base schema remain in effect for fields that are present.

    Usage:
    - Use this model as the request body type for endpoints that modify a user's
        goal. Omitted fields will remain unchanged; fields explicitly set to None
        will be applied if None is an allowed value.

    Notes:
    - For creating new goals, prefer the creation schema (e.g., UserGoalCreate)
        to ensure required fields are provided.
    """


class UserGoalRead(UserGoalBase):
    """
    Read schema for a user's goal.

    Extends UserGoalBase and exposes read-only identifiers:
    - id (StrictInt): Unique identifier for the user goal.
    - user_id (StrictInt): Identifier of the user who owns this goal.

    Intended for API responses and other read operations where validated,
    serializable goal data is required.
    """

    id: StrictInt
    user_id: StrictInt


class UserGoalProgress(BaseModel):
    goal_id: StrictInt
    interval: Interval
    activity_type: ActivityType
    goal_type: GoalType
    start_date: str
    end_date: str
    percentage_completed: NonNegInt | None = None
    # total
    total_calories: NonNegInt | None = None
    total_activities_number: NonNegInt | None = None
    total_distance: NonNegInt | None = None
    total_elevation: NonNegInt | None = None
    total_duration: NonNegInt | None = None
    # goal
    goal_calories: NonNegInt | None = None
    goal_activities_number: NonNegInt | None = None
    goal_distance: NonNegInt | None = None
    goal_elevation: NonNegInt | None = None
    goal_duration: NonNegInt | None = None
