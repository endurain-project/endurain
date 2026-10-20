"""Gear components schema definitions."""

from datetime import date
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

#: Update fields whose column is NOT NULL: a partial update may omit them but not clear them.
_NOT_CLEARABLE_FIELDS: tuple[str, ...] = ("purchase_date", "active")


class GearComponentBase(BaseModel):
    """Base model for gear component data.

    Attributes:
        gear_id: Foreign key to gear table.
        type: Type of gear component.
        brand: Gear component brand.
        model: Gear component model name.
        purchase_date: Purchase date (calendar date, no time of day).
        retired_date: Retired date (calendar date, no time of day).
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
    """Schema for reading a gear component.

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
    """Schema for updating a gear component.

    Attributes:
        id: Unique identifier.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier",
    )

    @model_validator(mode="after")
    def _reject_clearing_required_fields(self) -> Self:
        """Reject an explicit null for a field the component must always have.

        Returns:
            The validated update.

        Raises:
            ValueError: If ``purchase_date`` or ``active`` is sent as null.
        """
        cleared = [
            name for name in _NOT_CLEARABLE_FIELDS if name in self.model_fields_set and getattr(self, name) is None
        ]
        if cleared:
            raise ValueError(f"{', '.join(cleared)} cannot be null")
        return self


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
