"""User privacy settings Pydantic schemas and validators."""

from enum import IntEnum
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
)


class ActivityVisibility(IntEnum):
    """
    Activity visibility levels.

    Attributes:
        PUBLIC: Visible to everyone.
        FOLLOWERS: Visible only to followers.
        PRIVATE: Visible only to the user.
    """

    PUBLIC = 0
    FOLLOWERS = 1
    PRIVATE = 2


class UsersPrivacySettingsBase(BaseModel):
    """
    Base schema for user privacy settings.

    Attributes:
        default_activity_visibility: Default activity visibility
            level.
        hide_activity_start_time: Hide start time from
            activities.
        hide_activity_location: Hide location data from
            activities.
        hide_activity_map: Hide map visualization from
            activities.
        hide_activity_hr: Hide heart rate data from activities.
        hide_activity_power: Hide power data from activities.
        hide_activity_cadence: Hide cadence data from
            activities.
        hide_activity_elevation: Hide elevation data from
            activities.
        hide_activity_speed: Hide speed data from activities.
        hide_activity_pace: Hide pace data from activities.
        hide_activity_laps: Hide lap data from activities.
        hide_activity_workout_sets_steps: Hide workout sets and
            steps from activities.
        hide_activity_gear: Hide gear information from
            activities.
    """

    default_activity_visibility: ActivityVisibility | None = Field(
        ActivityVisibility.PUBLIC,
        description=(
            "Default activity visibility (0=public, 1=followers, " "2=private)"
        ),
    )
    hide_activity_start_time: StrictBool | None = Field(
        False, description="Hide activity start time"
    )
    hide_activity_location: StrictBool | None = Field(
        False, description="Hide activity location"
    )
    hide_activity_map: StrictBool | None = Field(False, description="Hide activity map")
    hide_activity_hr: StrictBool | None = Field(
        False, description="Hide activity heart rate"
    )
    hide_activity_power: StrictBool | None = Field(
        False, description="Hide activity power"
    )
    hide_activity_cadence: StrictBool | None = Field(
        False, description="Hide activity cadence"
    )
    hide_activity_elevation: StrictBool | None = Field(
        False, description="Hide activity elevation"
    )
    hide_activity_speed: StrictBool | None = Field(
        False, description="Hide activity speed"
    )
    hide_activity_pace: StrictBool | None = Field(
        False, description="Hide activity pace"
    )
    hide_activity_laps: StrictBool | None = Field(
        False, description="Hide activity laps"
    )
    hide_activity_workout_sets_steps: StrictBool | None = Field(
        False, description="Hide activity workout sets and steps"
    )
    hide_activity_gear: StrictBool | None = Field(
        False, description="Hide activity gear"
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class UsersPrivacySettingsCreate(UsersPrivacySettingsBase):
    """
    Pydantic model for creating user privacy settings.

    Inherits all attributes from UsersPrivacySettingsBase.
    """


class UsersPrivacySettingsUpdate(UsersPrivacySettingsBase):
    """
    Schema for updating user privacy settings.

    Inherits all validation from UsersPrivacySettingsBase.
    All fields are optional for partial updates.
    """


class UsersPrivacySettingsRead(UsersPrivacySettingsBase):
    """
    Schema for reading user privacy settings.

    Attributes:
        id: Unique identifier for the privacy settings record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(
        ..., ge=1, description="Unique identifier for privacy settings"
    )
    user_id: StrictInt = Field(
        ..., ge=1, description="Foreign key reference to the user"
    )
