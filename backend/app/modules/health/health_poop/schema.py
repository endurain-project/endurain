"""Pydantic schemas for health poop (bowel movement) data.

This module defines the request/response schemas for bowel
movement tracking, including validation rules, Bristol Stool
Scale types, and color enumerations.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)

import core.partial_update as core_partial_update
import core.types as core_types
from core.stored_enum import StoredStrEnum


class Source(Enum):
    """Enumeration of data sources for poop records.

    Attributes:
        MANUAL: Manually entered data.
    """

    MANUAL = "manual"


class BristolType(StoredStrEnum):
    """Bristol Stool Scale classification types; ``stored`` is the scale number kept in the database.

    Attributes:
        TYPE_1: Separate hard lumps (severe constipation).
        TYPE_2: Lumpy and sausage-like (mild constipation).
        TYPE_3: Sausage shape with cracks (normal).
        TYPE_4: Smooth, soft sausage (normal, ideal).
        TYPE_5: Soft blobs with clear edges (lacking fiber).
        TYPE_6: Mushy with ragged edges (mild diarrhea).
        TYPE_7: Liquid, no solid pieces (severe diarrhea).
    """

    TYPE_1 = ("type_1", 1)
    TYPE_2 = ("type_2", 2)
    TYPE_3 = ("type_3", 3)
    TYPE_4 = ("type_4", 4)
    TYPE_5 = ("type_5", 5)
    TYPE_6 = ("type_6", 6)
    TYPE_7 = ("type_7", 7)


#: The Bristol type as a model that validates with ``use_enum_values`` holds it: the member, which knows the scale
#: number the database stores.
_BristolTypeMember = Annotated[BristolType, AfterValidator(BristolType.from_value)]

#: The Bristol type of a stored row or an archive written before the types were strings, which hand over the
#: scale number. A client writes the plain enum, which refuses the number.
StoredBristolType = Annotated[_BristolTypeMember, BeforeValidator(BristolType.accept_stored)]


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
        bristol_type: Bristol Stool Scale type.
        color: Stool color description.
        notes: Optional notes about the bowel movement.
    """

    date_time: datetime | None = Field(
        default=None,
        description="Date and time of the bowel movement",
    )
    bristol_type: StoredBristolType | None = Field(
        default=None,
        description="Bristol Stool Scale type",
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

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


class HealthPoopWrite(HealthPoopBase):
    """Poop fields a client writes: the time is bounded, which a stored row read back need not be."""

    bristol_type: _BristolTypeMember | None = Field(
        default=None,
        description="Bristol Stool Scale type",
    )

    date_time: core_types.RecordInstant | None = Field(
        default=None,
        description="Date and time of the bowel movement, with a UTC offset",
    )


class HealthPoopCreate(HealthPoopWrite):
    """Schema for creating a new poop record.

    Requires date_time.
    """

    date_time: core_types.RecordInstant = Field(
        ...,
        description="Date and time of the bowel movement, with a UTC offset",
    )


class HealthPoopRead(HealthPoopBase):
    """Schema for reading a poop record.

    Attributes:
        source: Source of the data.
        id: Unique identifier for the poop record.
        user_id: Foreign key reference to the user.
    """

    source: Source | None = Field(
        default=None,
        description="Source of the data",
    )
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


class HealthPoopImport(HealthPoopCreate):
    """Poop record written by the server itself: a profile import, or a client's record with its assigned source.

    Unlike :class:`HealthPoopCreate` it carries the provenance, which a client never sets. Every
    server-side writer of ``source`` takes ``Health<Kind>Import`` (create) or ``Health<Kind>ImportUpdate``. A record
    without a source is a manual one.

    Attributes:
        source: The source the record came from; ``manual`` when none is given.
    """

    bristol_type: StoredBristolType | None = Field(
        default=None,
        description="Bristol Stool Scale type",
    )
    source: Source | None = Field(default=None, description="Source of the data")
    date_time: core_types.ImportedInstant = Field(..., description="Date and time of the bowel movement")

    @model_validator(mode="after")
    def set_default_source(self) -> "HealthPoopImport":
        """Make a record without a source a manual one.

        Returns:
            The validated model instance with the source set.
        """
        if self.source is None:
            self.source = Source.MANUAL
        return self
