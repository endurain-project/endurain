"""User privacy settings Pydantic schemas and validators."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
)

import core.partial_update as core_partial_update
import modules.activities.activity.constants as activity_constants


class UserPrivacySettingsBase(BaseModel):
    """Base schema for user privacy settings.

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
        discoverable: Appear in other users' username search.
    """

    default_activity_visibility: activity_constants.ActivityVisibility | None = Field(
        default=activity_constants.ActivityVisibility.PRIVATE,
        description="Default activity visibility (public, followers, private)",
    )
    hide_activity_start_time: StrictBool | None = Field(default=False, description="Hide activity start time")
    hide_activity_location: StrictBool | None = Field(default=False, description="Hide activity location")
    hide_activity_map: StrictBool | None = Field(default=False, description="Hide activity map")
    hide_activity_hr: StrictBool | None = Field(default=False, description="Hide activity heart rate")
    hide_activity_power: StrictBool | None = Field(default=False, description="Hide activity power")
    hide_activity_cadence: StrictBool | None = Field(default=False, description="Hide activity cadence")
    hide_activity_elevation: StrictBool | None = Field(default=False, description="Hide activity elevation")
    hide_activity_speed: StrictBool | None = Field(default=False, description="Hide activity speed")
    hide_activity_pace: StrictBool | None = Field(default=False, description="Hide activity pace")
    hide_activity_laps: StrictBool | None = Field(default=False, description="Hide activity laps")
    hide_activity_workout_sets_steps: StrictBool | None = Field(
        default=False, description="Hide activity workout sets and steps"
    )
    hide_activity_gear: StrictBool | None = Field(default=False, description="Hide activity gear")
    discoverable: StrictBool | None = Field(default=True, description="Appear in other users' username search")

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class UserPrivacySettingsCreate(UserPrivacySettingsBase):
    """Pydantic model for creating user privacy settings.

    Inherits all attributes from UserPrivacySettingsBase.
    """


class UserPrivacySettingsUpdate(core_partial_update.NotClearable, UserPrivacySettingsBase):
    """Schema for updating user privacy settings.

    Inherits all validation from UserPrivacySettingsBase.
    All fields are optional for partial updates.
    """

    not_clearable = (
        "default_activity_visibility",
        "hide_activity_start_time",
        "hide_activity_location",
        "hide_activity_map",
        "hide_activity_hr",
        "hide_activity_power",
        "hide_activity_cadence",
        "hide_activity_elevation",
        "hide_activity_speed",
        "hide_activity_pace",
        "hide_activity_laps",
        "hide_activity_workout_sets_steps",
        "hide_activity_gear",
        "discoverable",
    )


class UserPrivacySettingsRead(UserPrivacySettingsBase):
    """Schema for reading user privacy settings.

    Attributes:
        id: Unique identifier for the privacy settings record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(..., ge=1, description="Unique identifier for privacy settings")
    user_id: StrictInt = Field(..., ge=1, description="Foreign key reference to the user")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")
