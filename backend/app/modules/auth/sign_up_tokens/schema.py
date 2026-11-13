"""Pydantic schemas for sign-up token operations."""

import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

import modules.users.users.schema as users_schema


class SignUpToken(BaseModel):
    """Schema representing a sign-up token record.

    Attributes:
        id: Unique identifier for the token.
        user_id: ID of the user who signed up.
        token_hash: Hashed token value.
        created_at: Timestamp when token was created.
        expires_at: Timestamp when the token expires.
        used: Whether the token has been used.
        email: Email address the token proves.
        previous_email: Account email address a pending email change replaces.
        security_generation: Account security generation a pending email change was requested under.
        change_id: Identifier of the email change the token belongs to.
        revert_until: End of the email change's revert window.
        confirmed_at: When the token was confirmed, or the email change it records was applied.
    """

    id: StrictStr = Field(
        ...,
        description="Unique identifier for the token",
        max_length=64,
    )
    user_id: uuid.UUID = Field(
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
    email: StrictStr | None = Field(
        default=None,
        description="Email address the token proves",
        max_length=250,
    )
    previous_email: StrictStr | None = Field(
        default=None,
        description="Account email address a pending email change replaces",
        max_length=250,
    )
    security_generation: StrictInt | None = Field(
        default=None,
        description="Account security generation a pending email change was requested under",
    )
    change_id: StrictStr | None = Field(
        default=None,
        description="Identifier of the email change the token belongs to",
        max_length=64,
    )
    revert_until: datetime | None = Field(
        default=None,
        description="End of the email change's revert window",
    )
    confirmed_at: datetime | None = Field(
        default=None,
        description="When the token was confirmed, or the email change it records was applied",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class SignUpConfirm(BaseModel):
    """Request schema for confirming a sign-up.

    Attributes:
        token: The token of the sign-up link emailed to the new account.
        password: The password the user chooses for the account.
    """

    token: StrictStr = Field(
        ...,
        description=("The token of the sign-up link emailed to the new account"),
        min_length=1,
        max_length=256,
    )

    password: users_schema.UserPassword

    model_config = ConfigDict(extra="forbid")


class EmailChangeConfirm(BaseModel):
    """Request schema for confirming an email change.

    Attributes:
        token: The token of the link emailed to the new address.
    """

    token: StrictStr = Field(
        ...,
        description="The token of the link emailed to the new address",
        min_length=1,
        max_length=256,
    )

    model_config = ConfigDict(extra="forbid")


class EmailChangeCancel(BaseModel):
    """Request schema for reporting an email change as not made by the account's owner.

    Attributes:
        token: The token of the link emailed to the account's current address.
    """

    token: StrictStr = Field(
        ...,
        description="The token of the link emailed to the account's current address",
        min_length=1,
        max_length=256,
    )

    model_config = ConfigDict(extra="forbid")


class EmailChangeCancelRead(BaseModel):
    """Response schema for the "this wasn't me" link of an email change.

    Attributes:
        change_applied: Whether the change, or a later change of the account voided by the link, had been confirmed
            when the link was used.
        email_restored: Whether the account's previous address was put back; false when the change was still pending,
            or when another account holds the previous address now.
    """

    change_applied: StrictBool = Field(
        ..., description="Whether the change, or a later change voided by the link, had been confirmed"
    )
    email_restored: StrictBool = Field(..., description="Whether the account's previous email address was restored")

    model_config = ConfigDict(extra="forbid")


class SignUpResend(BaseModel):
    """Request schema for sending a sign-up's verification email again.

    Attributes:
        email: The address the sign-up used.
    """

    email: users_schema.UserEmail

    model_config = ConfigDict(extra="forbid")


class SignUpNextStep(StrEnum):
    """What a client does after a sign-up request, a resend or a confirmation.

    Attributes:
        SIGN_IN: The account is ready; the user signs in.
        CHECK_EMAIL: A verification email was sent; the user opens its link.
        AWAIT_APPROVAL: An administrator must approve the account before it can sign in.
    """

    SIGN_IN = "sign_in"
    CHECK_EMAIL = "check_email"
    AWAIT_APPROVAL = "await_approval"


class SignUpRead(BaseModel):
    """Response schema for sign-up operations.

    Attributes:
        next_step: What the client does next.
    """

    next_step: SignUpNextStep = Field(
        ...,
        description="What the client does next: sign in, check the email for a verification link, or wait for an "
        "administrator's approval",
    )

    model_config = ConfigDict(extra="forbid")
