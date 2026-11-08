"""User weekly streak settings Pydantic schemas."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
)

from modules.activities.activity.constants import ACTIVITY_ID_TO_NAME

MIN_ACTIVITIES_PER_WEEK_LIMIT = 21
"""Upper bound for the weekly activity target (3 per day)."""


class UsersStreakSettingsBase(BaseModel):
    """
    Shared fields for weekly streak settings.

    Attributes:
        min_activities_per_week: Activities needed in a week
            for it to count toward the streak.
        activity_types: Activity type IDs counted toward the
            streak, or None to count every type.
        show_on_profile: Whether other users can see the
            streak on the user's profile.
    """

    min_activities_per_week: StrictInt = Field(
        default=1,
        ge=1,
        le=MIN_ACTIVITIES_PER_WEEK_LIMIT,
        description="Activities needed in a week to keep the streak",
    )
    activity_types: list[StrictInt] | None = Field(
        default=None,
        description="Activity type IDs counted for the streak (null = all types)",
    )
    show_on_profile: StrictBool = Field(
        default=False,
        description="Show the streak to other users on the profile",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )

    @field_validator("activity_types")
    @classmethod
    def validate_activity_types(cls, value: list[int] | None) -> list[int] | None:
        """
        Validate and normalise the activity type list.

        An empty list is treated as "all types" (None) so the
        streak can never be configured into an impossible state.
        Duplicates are removed and the list is sorted.

        Args:
            value: Raw list of activity type IDs, or None.

        Returns:
            Sorted, de-duplicated list of IDs, or None.

        Raises:
            ValueError: If an ID is not a known activity type.
        """
        if value is None or len(value) == 0:
            return None
        unknown = sorted({type_id for type_id in value if type_id not in ACTIVITY_ID_TO_NAME})
        if unknown:
            raise ValueError(f"Unknown activity type IDs: {unknown}")
        return sorted(set(value))


class UsersStreakSettingsUpdate(UsersStreakSettingsBase):
    """Request body for replacing the user's streak settings."""


class UsersStreakSettingsRead(UsersStreakSettingsBase):
    """
    Streak settings as returned by the API.

    Attributes:
        user_id: Owner of the settings.
    """

    user_id: StrictInt = Field(..., description="User ID that owns the settings")
