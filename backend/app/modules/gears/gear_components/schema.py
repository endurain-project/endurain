"""Gear components schema definitions."""

from datetime import datetime as datetime_type

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

BIKE_COMPONENT_TYPES: list[str] = [
    "back_break_oil",
    "back_break_pads",
    "back_break_rotor",
    "back_tire",
    "back_tube",
    "back_tubeless_sealant",
    "back_tubeless_rim_tape",
    "back_wheel",
    "back_wheel_valve",
    "bottom_bracket",
    "bottle_cage",
    "cassette",
    "chain",
    "computer_mount",
    "crank_left_power_meter",
    "crank_right_power_meter",
    "crankset",
    "crankset_power_meter",
    "fork",
    "frame",
    "front_break_oil",
    "front_break_pads",
    "front_break_rotor",
    "front_derailleur",
    "front_shifter",
    "front_tire",
    "front_tube",
    "front_tubeless_sealant",
    "front_tubeless_rim_tape",
    "front_wheel",
    "front_wheel_valve",
    "grips",
    "handlebar",
    "handlebar_tape",
    "headset",
    "pedals",
    "pedals_left_power_meter",
    "pedals_power_meter",
    "pedals_right_power_meter",
    "rear_derailleur",
    "rear_shifter",
    "saddle",
    "seatpost",
    "stem",
]

SHOES_COMPONENT_TYPES: list[str] = [
    "cleats",
    "insoles",
    "laces",
]

RACQUET_COMPONENT_TYPES: list[str] = [
    "basegrip",
    "bumpers",
    "grommets",
    "overgrip",
    "strings",
]

WINDSURF_COMPONENT_TYPES: list[str] = [
    "sail",
    "board",
    "mast",
    "boom",
    "mast_extension",
    "mast_base",
    "mast_universal_joint",
    "fin",
    "footstraps",
    "harness_lines",
    "rigging_lines",
    "footpad",
    "impact_vest",
    "lifeguard_vest",
    "helmet",
    "wing",
    "front_foil",
    "stabilizer",
    "fuselage",
]


class GearComponentBase(BaseModel):
    """
    Base model for gear component data.

    Attributes:
        gear_id: Foreign key to gear table.
        type: Type of gear component.
        brand: Gear component brand.
        model: Gear component model name.
        purchase_date: Purchase date.
        retired_date: Retired date.
        active: Whether component is active.
        expected_kms: Expected kilometers.
        purchase_value: Purchase value.
    """

    gear_id: StrictInt = Field(
        ...,
        description="Foreign key to gear",
    )
    type: StrictStr = Field(
        ...,
        max_length=250,
        description="Type of gear component",
    )
    brand: StrictStr = Field(
        ...,
        max_length=250,
        description="Gear component brand",
    )
    model: StrictStr = Field(
        ...,
        max_length=250,
        description="Gear component model",
    )
    purchase_date: datetime_type | None = Field(
        default=None,
        description="Purchase date",
    )
    retired_date: datetime_type | None = Field(
        default=None,
        description="Retired date",
    )
    active: StrictBool | None = Field(
        default=None,
        description=("Whether the component is active"),
    )
    expected_kms: StrictInt | None = Field(
        default=None,
        ge=0,
        description=("Expected kilometers"),
    )
    purchase_value: StrictFloat | None = Field(
        default=None,
        ge=0,
        description="Purchase value",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class GearComponentCreate(GearComponentBase):
    """Schema for creating a gear component."""


class GearComponentRead(GearComponentBase):
    """
    Schema for reading a gear component.

    Attributes:
        id: Unique identifier.
        user_id: Foreign key to user.
        current_distance: Accumulated distance.
        current_time: Accumulated time.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier",
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key to user",
    )
    current_distance: StrictFloat = Field(
        default=0,
        ge=0,
        description=("Accumulated activity distance in meters"),
    )
    current_time: StrictFloat = Field(
        default=0,
        ge=0,
        description=("Accumulated activity time in seconds"),
    )


class GearComponentUpdate(GearComponentBase):
    """
    Schema for updating a gear component.

    Attributes:
        id: Unique identifier.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier",
    )


class GearComponentTypesRead(BaseModel):
    """
    Schema for reading component type lists.

    Attributes:
        bike: Valid bike component types.
        shoes: Valid shoes component types.
        racquet: Valid racquet component types.
        windsurf: Valid windsurf component types.
    """

    bike: list[str] = Field(
        ...,
        description=("Valid bike component types"),
    )
    shoes: list[str] = Field(
        ...,
        description=("Valid shoes component types"),
    )
    racquet: list[str] = Field(
        ...,
        description=("Valid racquet component types"),
    )
    windsurf: list[str] = Field(
        ...,
        description=("Valid windsurf component types"),
    )

    model_config = ConfigDict(
        extra="forbid",
    )
