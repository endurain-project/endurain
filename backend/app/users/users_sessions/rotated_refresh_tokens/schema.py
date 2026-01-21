"""Rotated refresh token Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


class RotatedRefreshTokenCreate(BaseModel):
    """
    Schema for creating a rotated refresh token record.

    Attributes:
        token_family_id: UUID of the token family.
        hashed_token: Hashed old refresh token.
        rotation_count: Sequential rotation number for this
            token.
        rotated_at: Timestamp when this token was rotated.
        expires_at: Cleanup marker timestamp.
    """

    token_family_id: StrictStr = Field(
        ...,
        max_length=36,
        description="UUID of the token family",
    )
    hashed_token: StrictStr = Field(
        ...,
        max_length=255,
        description="Hashed old refresh token",
    )
    rotation_count: StrictInt = Field(
        ...,
        ge=0,
        description="Which rotation this token belonged to",
    )
    rotated_at: datetime = Field(
        ...,
        description="When this token was rotated",
    )
    expires_at: datetime = Field(
        ...,
        description="Cleanup marker (rotated_at + 60 seconds)",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class RotatedRefreshTokenRead(RotatedRefreshTokenCreate):
    """
    Schema for reading a rotated refresh token record.

    Attributes:
        id: Unique identifier for the rotated token record.
    """

    id: StrictInt = Field(
        ...,
        ge=1,
        description="Unique identifier for the rotated token record",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
