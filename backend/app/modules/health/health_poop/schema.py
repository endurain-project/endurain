"""Pydantic schemas for health poop (bowel movement) data.

This module defines the request/response schemas for bowel
movement tracking, including validation rules, Bristol Stool
Scale types, and color enumerations.
"""

from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)

import core.partial_update as core_partial_update
import core.types as core_types


class Source(Enum):
    """Enumeration of data sources for poop records.

    Attributes:
        MANUAL: Manually entered data.
    """

    MANUAL = "manual"


class BristolType(Enum):
    """Bristol Stool Scale classification types.

    Attributes:
        TYPE_1: Separate hard lumps (severe constipation).
        TYPE_2: Lumpy and sausage-like (mild constipation).
        TYPE_3: Sausage shape with cracks (normal).
        TYPE_4: Smooth, soft sausage (normal, ideal).
        TYPE_5: Soft blobs with clear edges (lacking fiber).
        TYPE_6: Mushy with ragged edges (mild diarrhea).
        TYPE_7: Liquid, no solid pieces (severe diarrhea).
    """

    TYPE_1 = 1
    TYPE_2 = 2
    TYPE_3 = 3
    TYPE_4 = 4
    TYPE_5 = 5
    TYPE_6 = 6
    TYPE_7 = 7


class Color(Enum):
    """Enumeration of common stool color descriptions.

    Attributes:
        BROWN: Normal brown color.
        DARK_BROWN: Darker than normal brown.
        LIGHT_BROWN: Lighter than normal brown.
        YELLOW: Yellowish color.
        GREEN: Greenish color.
        BLACK: Black or very dark color.
        RED: Red or reddish color.
        WHITE: White or clay-colored.
    """

    BROWN = "brown"
    DARK_BROWN = "dark_brown"
    LIGHT_BROWN = "light_brown"
    YELLOW = "yellow"
    GREEN = "green"
    BLACK = "black"
    RED = "red"
    WHITE = "white"


class HealthPoopBase(BaseModel):
    """Base model for health poop data.

    Attributes:
        date_time: Date and time of the bowel movement.
        bristol_type: Bristol Stool Scale type (1-7).
        color: Stool color description.
        notes: Optional notes about the bowel movement.
        source: Source of the data.
    """

    date_time: datetime | None = Field(
        default=None,
        description="Date and time of the bowel movement",
    )
    bristol_type: BristolType | None = Field(
        default=None,
        description="Bristol Stool Scale type (1-7)",
    )
    color: Color | None = Field(
        default=None,
        description="Stool color description",
    )
    notes: StrictStr | None = Field(
        default=None,
        max_length=500,
        description=("Optional notes about the bowel movement"),
    )
    source: Source | None = Field(
        default=None,
        description="Source of the data",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthPoopWrite(HealthPoopBase):
    """Poop fields a client writes: the time is bounded, which a stored row read back need not be."""

    date_time: core_types.RecordDateTime | None = Field(
        default=None,
        description="Date and time of the bowel movement",
    )


class HealthPoopCreate(HealthPoopWrite):
    """Schema for creating a new poop record.

    Requires date_time and sets defaults for source.
    """

    date_time: core_types.RecordDateTime = Field(
        ...,
        description="Date and time of the bowel movement",
    )

    @model_validator(mode="after")
    def set_defaults_and_validate(
        self,
    ) -> "HealthPoopCreate":
        """Set the defaults of the fields left out.

        Returns:
            The validated model instance with defaults set.
        """
        if self.source is None:
            self.source = Source.MANUAL
        return self


class HealthPoopRead(HealthPoopBase):
    """Schema for reading a poop record.

    Attributes:
        id: Unique identifier for the poop record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(
        ...,
        description=("Unique identifier for the poop record"),
    )
    date_time: datetime = Field(
        ...,
        description="Date and time of the bowel movement",
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key reference to the user",
    )
    version: StrictInt = Field(default=1, ge=1, description="Optimistic-concurrency counter, also sent as the ETag")


class HealthPoopUpdate(core_partial_update.NotClearable, HealthPoopWrite):
    """Schema for the fields a PATCH changes on a poop record.

    The record is named by the path, so the body carries neither an id nor an owner; only the
    fields present are changed.
    """

    not_clearable = ("date_time",)
