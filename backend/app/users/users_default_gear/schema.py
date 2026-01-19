"""User default gear Pydantic schemas."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
)


class UsersDefaultGearBase(BaseModel):
    """
    Base schema for users default gear assignments.

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

    run_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for run activities",
    )
    trail_run_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for trail run activities",
    )
    virtual_run_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for virtual run activities",
    )
    ride_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for ride activities",
    )
    gravel_ride_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for gravel ride activities",
    )
    mtb_ride_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for MTB ride activities",
    )
    virtual_ride_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for virtual ride activities",
    )
    ows_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for OWS activities",
    )
    walk_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for walk activities",
    )
    hike_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for hike activities",
    )
    tennis_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for tennis activities",
    )
    alpine_ski_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for alpine ski activities",
    )
    nordic_ski_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for nordic ski activities",
    )
    snowboard_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for snowboard activities",
    )
    windsurf_gear_id: StrictInt | None = Field(
        None,
        ge=1,
        description="Default gear for windsurf activities",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class UsersDefaultGearRead(UsersDefaultGearBase):
    """
    Schema for reading user default gear settings.

    Extends base with identifier fields.

    Attributes:
        id: Unique identifier for the record.
        user_id: User ID reference.
    """

    id: StrictInt = Field(..., ge=1, description="Unique identifier")
    user_id: StrictInt = Field(..., ge=1, description="User ID")


class UsersDefaultGearUpdate(UsersDefaultGearRead):
    """
    Schema for updating user default gear settings.

    Inherits all gear assignment fields from read schema.
    All fields are optional for partial updates.
    """
