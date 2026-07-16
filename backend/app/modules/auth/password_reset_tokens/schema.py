"""Pydantic schemas for password reset token operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictBool, StrictInt, StrictStr


class PasswordResetToken(BaseModel):
    """
    Schema representing a password reset token record.

    Attributes:
        id: Unique identifier for the token.
        user_id: ID of the user who requested the reset.
        token_hash: Hashed token value.
        created_at: Timestamp when the token was created.
        expires_at: Timestamp when the token expires.
        used: Whether the token has already been used.
    """

    id: StrictStr = Field(
        ...,
        description="Unique identifier for the token",
        max_length=64,
    )
    user_id: StrictInt = Field(
        ...,
        description="ID of the user who requested the reset",
    )
    token_hash: StrictStr = Field(
        ...,
        description="Hashed token value",
        max_length=128,
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when the token was created",
    )
    expires_at: datetime = Field(
        ...,
        description="Timestamp when the token expires",
    )
    used: StrictBool = Field(
        ...,
        description="Whether the token has already been used",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class PasswordResetRequest(BaseModel):
    """
    Request schema for initiating a password reset.

    Attributes:
        email: Email address for the reset.
    """

    email: EmailStr = Field(
        ...,
        description="Email address for the reset",
    )

    model_config = ConfigDict(extra="forbid")


class PasswordResetConfirm(BaseModel):
    """
    Request schema for confirming a password reset.

    Attributes:
        token: The reset token received by the user.
        new_password: The new password to set.
    """

    token: StrictStr = Field(
        ...,
        description="The reset token received by the user",
        min_length=1,
        max_length=256,
    )
    new_password: StrictStr = Field(
        ...,
        description="The new password to set",
        min_length=8,
        max_length=256,
    )

    model_config = ConfigDict(extra="forbid")


class PasswordResetResponse(BaseModel):
    """
    Response schema for password reset operations.

    Attributes:
        message: Informational message for the client.
    """

    message: StrictStr = Field(
        ...,
        description="Informational message for the client",
    )

    model_config = ConfigDict(extra="forbid")
