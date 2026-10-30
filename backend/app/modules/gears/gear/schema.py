"""Gear schema definitions."""

from datetime import datetime as datetime_type
from enum import IntEnum
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)


class GearType(IntEnum):
    """Supported gear type codes.

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


#: The largest value of a ``Numeric(11, 2)`` column (``initial_kms``, ``purchase_value``).
MAX_AMOUNT = 999_999_999.99

#: Update fields whose column is NOT NULL: a partial update may omit them but not clear them.
_NOT_CLEARABLE_FIELDS: tuple[str, ...] = ("nickname", "gear_type", "created_at", "active", "initial_kms")


def _require_nickname(value: str) -> str:
    """Trim a nickname and reject one that is blank.

    Args:
        value: The submitted nickname.

    Returns:
        The trimmed nickname.

    Raises:
        ValueError: If nothing is left after trimming.
    """
    value = value.strip()
    if not value:
        raise ValueError("nickname cannot be blank")
    return value


def normalize_nickname(nickname: str) -> str:
    """Normalize a nickname for case-insensitive comparison.

    Args:
        nickname: The nickname to compare.

    Returns:
        The nickname trimmed and lower-cased, as the unique index compares it.
    """
    return str(nickname).lower().strip()


#: A nickname trimmed on input; blank is rejected.
RequiredNickname = Annotated[StrictStr, AfterValidator(_require_nickname)]


class GearBase(BaseModel):
    """Fields a client may set on a gear.

    Attributes:
        brand: Gear brand name.
        model: Gear model name.
        nickname: Gear display nickname.
        gear_type: Gear type identifier.
        created_at: Gear creation timestamp.
        active: Whether the gear is active.
        initial_kms: Initial kilometers.
        purchase_value: Purchase value.
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
        le=MAX_AMOUNT,
        description="Initial kilometers",
    )
    purchase_value: StrictFloat | None = Field(
        default=None,
        ge=0,
        le=MAX_AMOUNT,
        description="Purchase value",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class GearCreateRequest(GearBase):
    """Request body for creating a gear.

    Provider gear IDs are not accepted: only the Strava and Garmin Connect syncs and
    the profile import set them, so a client cannot forge a provider link.
    """

    nickname: RequiredNickname = Field(
        ...,
        max_length=250,
        description="Gear display nickname",
    )


class GearCreate(GearBase):
    """A gear to create, as built by the provider syncs and the profile import.

    Attributes:
        user_id: Foreign key to user; ignored on write, the owner is passed explicitly.
        strava_gear_id: Strava gear ID.
        garminconnect_gear_id: Garmin Connect gear ID.
    """

    user_id: StrictInt | None = Field(
        default=None,
        description="Foreign key to user",
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


class GearRead(GearCreate):
    """Schema for reading a gear record.

    Attributes:
        id: Unique identifier.
        user_id: Foreign key to user.
        version: Optimistic-concurrency counter, also sent as the ``ETag``.
    """

    id: StrictInt = Field(
        ...,
        description="Unique identifier",
    )
    user_id: StrictInt = Field(
        ...,
        description="Foreign key to user",
    )
    version: StrictInt = Field(
        default=1,
        ge=1,
        description="Optimistic-concurrency counter",
    )


class GearDetailRead(GearRead):
    """Extended gear with computed stats.

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
    """Partial update of a gear: omit a field to keep it, send null to clear a nullable one.

    The gear comes from the path; provider gear IDs cannot be changed.
    """

    nickname: RequiredNickname | None = Field(
        default=None,
        max_length=250,
        description="Gear display nickname",
    )
    gear_type: GearType | None = Field(
        default=None,
        description="Gear type identifier",
    )

    @model_validator(mode="after")
    def _reject_clearing_required_fields(self) -> Self:
        """Reject an explicit null for a field the gear must always have.

        Returns:
            The validated update.

        Raises:
            ValueError: If a required field is sent as null.
        """
        cleared = [
            name for name in _NOT_CLEARABLE_FIELDS if name in self.model_fields_set and getattr(self, name) is None
        ]
        if cleared:
            raise ValueError(f"{', '.join(cleared)} cannot be null")
        return self
