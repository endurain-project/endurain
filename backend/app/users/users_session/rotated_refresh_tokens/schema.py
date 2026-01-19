from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class RotatedRefreshTokenCreate(BaseModel):
    """
    Schema for creating a rotated refresh token record for security audit and reuse detection.

    Attributes:
        token_family_id (str): UUID of the token family this token belongs to.
        hashed_token (str): Hashed old refresh token that was rotated out.
        rotation_count (int): Sequential rotation number for this token.
        rotated_at (datetime): Timestamp when this token was rotated.
        expires_at (datetime): Cleanup marker timestamp (rotated_at + 60 seconds).

    Config:
        from_attributes (bool): Allows model initialization from attributes.
        extra (str): Forbids extra fields not defined in the model.
        validate_assignment (bool): Enables validation on assignment.
    """

    token_family_id: str = Field(..., description="UUID of the token family")
    hashed_token: str = Field(..., description="Hashed old refresh token")
    rotation_count: int = Field(
        ..., description="Which rotation this token belonged to"
    )
    rotated_at: datetime = Field(..., description="When this token was rotated")
    expires_at: datetime = Field(
        ..., description="Cleanup marker (rotated_at + 60 seconds)"
    )

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )


class RotatedRefreshTokenRead(RotatedRefreshTokenCreate):
    """
    Schema for reading a rotated refresh token record from the database.

    Inherits all attributes from RotatedRefreshTokenCreate and adds:
        id (int): Unique identifier for the rotated token record.

    Config:
        from_attributes (bool): Allows model initialization from attributes.
        extra (str): Forbids extra fields not defined in the model.
        validate_assignment (bool): Enables validation on assignment.
    """

    id: int = Field(..., description="Unique identifier for the rotated token record")

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )
