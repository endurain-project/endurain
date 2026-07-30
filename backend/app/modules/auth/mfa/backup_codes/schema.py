"""Pydantic schemas for MFA backup code API responses."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class MFABackupCodesResponse(BaseModel):
    """Response payload returned after generating MFA backup codes.

    Attributes:
        codes: One-time backup codes shown to the user exactly once.
        created_at: Timestamp when the codes were generated.
    """

    model_config = ConfigDict(strict=True)

    codes: list[StrictStr] = Field(..., min_length=1, description="One-time backup codes")
    created_at: datetime


class MFABackupCodeStatus(BaseModel):
    """Aggregate status of a user's MFA backup codes.

    Attributes:
        has_codes: Whether the user currently has any backup codes.
        total: Total number of backup codes on record.
        unused: Number of backup codes still available.
        used: Number of backup codes already consumed.
        created_at: Timestamp when the current set of codes was generated.
    """

    model_config = ConfigDict(from_attributes=True, strict=True)

    has_codes: StrictBool
    total: StrictInt = Field(ge=0)
    unused: StrictInt = Field(ge=0)
    used: StrictInt = Field(ge=0)
    created_at: datetime | None = None
