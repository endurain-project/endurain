"""User default gear Pydantic schemas."""

import uuid

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)

import core.types as core_types


class UserDefaultGearBase(BaseModel):
    """Base schema for users default gear assignments.

    Attributes:
        run_gear_id: Default gear for run activities.
        trail_run_gear_id: Default gear for trail run
            activities.
        virtual_run_gear_id: Default gear for virtual run
            activities.
        ride_gear_id: Default gear for ride activities.
        gravel_ride_gear_id: Default gear for gravel ride
            activities.
        mtb_ride_gear_id: Default gear for MTB ride activities.
        virtual_ride_gear_id: Default gear for virtual ride
            activities.
        ows_gear_id: Default gear for open water swim
            activities.
        walk_gear_id: Default gear for walk activities.
        hike_gear_id: Default gear for hike activities.
        tennis_gear_id: Default gear for tennis activities.
        alpine_ski_gear_id: Default gear for alpine ski
            activities.
        nordic_ski_gear_id: Default gear for nordic ski
            activities.
        snowboard_gear_id: Default gear for snowboard
            activities.
        windsurf_gear_id: Default gear for windsurf activities.
    """

    run_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for run activities",
    )
    trail_run_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for trail run activities",
    )
    virtual_run_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for virtual run activities",
    )
    ride_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for ride activities",
    )
    gravel_ride_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for gravel ride activities",
    )
    mtb_ride_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for MTB ride activities",
    )
    virtual_ride_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for virtual ride activities",
    )
    ows_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for OWS activities",
    )
    walk_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for walk activities",
    )
    hike_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for hike activities",
    )
    tennis_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for tennis activities",
    )
    alpine_ski_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for alpine ski activities",
    )
    nordic_ski_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for nordic ski activities",
    )
    snowboard_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for snowboard activities",
    )
    windsurf_gear_id: core_types.RecordId | None = Field(
        default=None,
        description="Default gear for windsurf activities",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class UserDefaultGearRead(UserDefaultGearBase):
    """Schema for reading user default gear settings.

    Extends base with identifier fields.

    Attributes:
        id: Unique identifier for the record.
        user_id: User ID reference.
    """

    id: uuid.UUID = Field(..., description="Unique identifier")
    user_id: StrictInt = Field(..., ge=1, description="User ID")
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")


class UserDefaultGearUpdate(UserDefaultGearBase):
    """Schema for updating user default gear settings.

    Carries only the gear assignments, all optional for partial updates. The record is the
    authenticated user's own, so the body names neither the record nor the user.
    """
