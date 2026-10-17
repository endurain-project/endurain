"""Pydantic schemas for sign-up token operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr


class SignUpToken(BaseModel):
    """
    Schema representing a sign-up token record.

    Attributes:
        id: Unique identifier for the token.
        user_id: ID of the user who signed up.
        token_hash: Hashed token value.
        created_at: Timestamp when token was created.
        expires_at: Timestamp when the token expires.
        used: Whether the token has been used.
    """

    id: StrictStr = Field(
        ...,
        description="Unique identifier for the token",
        max_length=64,
    )
    user_id: StrictInt = Field(
        ...,
        description="ID of the user who signed up",
    )
    token_hash: StrictStr = Field(
        ...,
        description="Hashed token value",
        max_length=128,
    )
    created_at: datetime = Field(
        ...,
        description=("Timestamp when the token was created"),
    )
    expires_at: datetime = Field(
        ...,
        description=("Timestamp when the token expires"),
    )
    used: StrictBool = Field(
        ...,
        description="Whether the token has been used",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class SignUpConfirm(BaseModel):
    """
    Request schema for confirming a sign-up.

    Attributes:
        token: The sign-up token received by user.
    """

    token: StrictStr = Field(
        ...,
        description=("The sign-up token received by the user"),
        min_length=1,
        max_length=256,
    )

    model_config = ConfigDict(extra="forbid")


class SignUpResponse(BaseModel):
    """
    Response schema for sign-up operations.

    Attributes:
        message: Human-readable result message.
        email_verification_required: Whether email verification is required.
        admin_approval_required: Whether admin approval is required.
    """

    message: StrictStr = Field(
        ...,
        description="Human-readable result message",
    )
    email_verification_required: StrictBool | None = Field(
        default=None,
        description=("Whether email verification is required"),
    )
    admin_approval_required: StrictBool | None = Field(
        default=None,
        description=("Whether admin approval is required"),
    )

    model_config = ConfigDict(extra="forbid")
