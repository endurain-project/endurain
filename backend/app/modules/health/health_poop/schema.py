"""
Pydantic schemas for health poop (bowel movement) data.

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

import modules.health.schema as health_schema


class Source(Enum):
    """
    Enumeration of data sources for poop records.

    Attributes:
        MANUAL: Manually entered data.
    """

    MANUAL = "manual"


class BristolType(Enum):
    """
    Bristol Stool Scale classification types.

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
    """
    Enumeration of common stool color descriptions.

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
    """
    Base model for health poop data.

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


class HealthPoopCreate(HealthPoopBase):
    """
    Schema for creating a new poop record.

    Requires date_time and sets defaults for source.
    """

    @model_validator(mode="after")
    def set_defaults_and_validate(
        self,
    ) -> "HealthPoopCreate":
        """
        Validate required fields and set defaults.

        Returns:
            The validated model instance with defaults set.

        Raises:
            ValueError: If date_time is not provided.
        """
        if self.date_time is None:
            raise ValueError("date_time is required")
        if self.source is None:
            self.source = Source.MANUAL
        return self


class HealthPoopRead(HealthPoopBase):
    """
    Schema for reading a poop record.

    Attributes:
        id: Unique identifier for the poop record.
        user_id: Foreign key reference to the user.
    """

    id: StrictInt = Field(
        ...,
        description=("Unique identifier for the poop record"),
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key reference to the user",
    )


class HealthPoopUpdate(HealthPoopRead):
    """
    Schema for updating a poop record.

    Inherits from HealthPoopRead for consistency with read
    operations while allowing modifications to poop data.
    """


class HealthPoopListResponse(health_schema.HealthListResponse):
    """
    Response model for listing health poop records.

    Attributes:
        records: A list of HealthPoopRead objects representing
            individual bowel movement records.
    """

    records: list[HealthPoopRead] = Field(
        ...,
        description="List of health poop records",
    )
