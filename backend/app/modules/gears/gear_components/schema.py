"""Gear components schema definitions."""

from datetime import date

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

import core.partial_update as core_partial_update
import core.types as core_types

#: The largest value of the ``expected_usage`` column (meters or seconds), a 32-bit integer.
MAX_EXPECTED_USAGE = core_types.INT32_MAX


def is_retired_after_purchase(purchase_date: date | None, retired_date: date | None) -> bool:
    """Whether a retired date is acceptable next to a purchase date.

    Args:
        purchase_date: The purchase date, if given.
        retired_date: The retired date, if given.

    Returns:
        False only when both are given and the retired date is not later.
    """
    return retired_date is None or purchase_date is None or retired_date > purchase_date


class GearComponentBase(BaseModel):
    """Base model for the gear component fields a client may set.

    Attributes:
        type: Type of gear component.
        brand: Gear component brand.
        model: Gear component model name.
        purchase_date: Purchase date (calendar date, no time of day).
        retired_date: Retired date (calendar date, no time of day).
        active: Whether component is active.
        expected_usage: Wear threshold in meters for a distance-tracked gear and in seconds for a time-tracked one.
        purchase_value: Purchase price as a decimal string in the owner's currency.
    """

    type: StrictStr | None = Field(
        default=None,
        max_length=250,
        description="Type of gear component",
    )
    brand: StrictStr | None = Field(
        default=None,
        max_length=250,
        description="Gear component brand",
    )
    model: StrictStr | None = Field(
        default=None,
        max_length=250,
        description="Gear component model",
    )
    purchase_date: date | None = Field(
        default=None,
        description="Purchase date",
    )
    retired_date: date | None = Field(
        default=None,
        description="Retired date",
    )
    active: StrictBool | None = Field(
        default=None,
        description=("Whether the component is active"),
    )
    expected_usage: StrictInt | None = Field(
        default=None,
        ge=0,
        le=MAX_EXPECTED_USAGE,
        description=(
            "Wear threshold: meters of activity distance for a distance-tracked gear, seconds of activity time "
            "for a time-tracked one (racquet)"
        ),
    )
    purchase_value: core_types.Money | None = Field(
        default=None,
        description=(
            "Purchase price as a decimal string with two decimals, in the owner's currency "
            "(the `currency` user setting), such as 129.90"
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class GearComponentCreate(GearComponentBase):
    """Schema for creating a gear component.

    Attributes:
        gear_id: Foreign key to gear table.
    """

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
    gear_id: core_types.RecordId = Field(
        ...,
        description="Foreign key to gear",
    )


class GearComponentRead(GearComponentCreate):
    """Schema for reading a gear component.

    Attributes:
        id: Unique identifier.
        user_id: Foreign key to user.
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
    """

    version: StrictInt = Field(
        default=1,
        ge=1,
        description="Optimistic-concurrency counter",
    )
    id: StrictInt = Field(
        ...,
        description="Unique identifier",
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key to user",
    )


class GearComponentUsageRead(GearComponentRead):
    """A gear component with the usage it has accumulated, served by the per-gear list only.

    Attributes:
        current_distance: Accumulated distance in meters.
        current_time: Accumulated time in seconds.
    """

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


class GearComponentUpdate(core_partial_update.NotClearable, GearComponentBase):
    """Partial update of a gear component: omit a field to keep it, send null to clear a nullable one.

    The component and its gear come from the path and cannot be changed.
    """

    not_clearable = ("type", "brand", "model", "purchase_date", "active")


class GearComponentTypesRead(BaseModel):
    """Schema for reading component type lists.

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
