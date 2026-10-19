"""Gear schema definitions."""

from datetime import datetime as datetime_type
from enum import IntEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)


class GearType(IntEnum):
    """
    Supported gear type codes.

    Attributes:
        BIKE: Bicycle (1).
        SHOES: Running or walking shoes (2).
        WETSUIT: Wetsuit (3).
        RACQUET: Racquet (4).
        SKI: Skis (5).
        SNOWBOARD: Snowboard (6).
        WINDSURF: Windsurf board (7).
        WATER_SPORTS_BOARD: Water sports board (8).
    """

    BIKE = 1
    SHOES = 2
    WETSUIT = 3
    RACQUET = 4
    SKI = 5
    SNOWBOARD = 6
    WINDSURF = 7
    WATER_SPORTS_BOARD = 8


class GearBase(BaseModel):
    """
    Base model for gear data.

    Attributes:
        brand: Gear brand name.
        model: Gear model name.
        nickname: Gear display nickname.
        gear_type: Gear type identifier.
        created_at: Gear creation timestamp.
        active: Whether the gear is active.
        initial_kms: Initial kilometers.
        purchase_value: Purchase value.
        strava_gear_id: Strava gear ID.
        garminconnect_gear_id: Garmin gear ID.
    """

    brand: StrictStr | None = Field(
        default=None,
        max_length=250,
        description="Gear brand name",
    )
    model: StrictStr | None = Field(
        default=None,
        max_length=250,
        description="Gear model name",
    )
    nickname: StrictStr = Field(
        ...,
        max_length=250,
        description="Gear display nickname",
    )
    gear_type: GearType = Field(
        ...,
        description="Gear type identifier",
    )
    created_at: datetime_type | None = Field(
        default=None,
        description="Gear creation timestamp",
    )
    active: StrictBool | None = Field(
        default=None,
        description="Whether the gear is active",
    )
    initial_kms: StrictFloat | None = Field(
        default=None,
        ge=0,
        description="Initial kilometers",
    )
    purchase_value: StrictFloat | None = Field(
        default=None,
        ge=0,
        description="Purchase value",
    )
    strava_gear_id: StrictStr | None = Field(
        default=None,
        max_length=45,
        description="Strava gear ID",
    )
    garminconnect_gear_id: StrictStr | None = Field(
        default=None,
        max_length=45,
        description="Garmin Connect gear ID",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class GearCreate(GearBase):
    """
    Schema for creating a gear record.

    Attributes:
        user_id: Foreign key to user.
    """

    user_id: StrictInt | None = Field(
        default=None,
        description="Foreign key to user",
    )


class GearRead(GearBase):
    """
    Schema for reading a gear record.

    Attributes:
        id: Unique identifier.
        user_id: Foreign key to user.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier",
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key to user",
    )


class GearDetailRead(GearRead):
    """
    Extended gear with computed stats.

    Attributes:
        total_distance: Total distance (m).
        total_time: Total time (seconds).
        total_components_cost: Sum of parts.
    """

    total_distance: StrictFloat = Field(
        default=0,
        ge=0,
        description=("Total activity distance in meters"),
    )
    total_time: StrictFloat = Field(
        default=0,
        ge=0,
        description=("Total activity time in seconds"),
    )
    total_components_cost: StrictFloat = Field(
        default=0,
        ge=0,
        description=("Sum of component purchase values"),
    )


class GearUpdate(GearBase):
    """
    Schema for updating a gear record.

    Attributes:
        id: Unique identifier.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier",
    )


class GearsListResponse(BaseModel):
    """
    Response model for paginated gear listing.

    Attributes:
        total: Total number of gear records.
        num_records: Number of records returned.
        page_number: Current page number.
        records: List of gear records.
    """

    total: StrictInt = Field(
        ...,
        ge=0,
        description="Total number of gear records",
    )
    num_records: StrictInt | None = Field(
        default=None,
        ge=0,
        description="Number of records returned",
    )
    page_number: StrictInt | None = Field(
        default=None,
        ge=1,
        description="Current page number",
    )
    records: list[GearRead] = Field(
        ...,
        description="List of gear records",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
