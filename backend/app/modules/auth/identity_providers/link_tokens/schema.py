"""Pydantic schemas for IdP link tokens."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)


class IdpLinkTokenCreate(BaseModel):
    """Schema for creating an IdP link token."""

    id: StrictStr = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Random row ID",
    )
    token_hash: StrictStr = Field(
        ...,
        min_length=64,
        max_length=64,
        description="SHA-256 hash of the one-time link token",
    )
    user_id: StrictInt = Field(
        ...,
        gt=0,
        description="User ID linking the IdP",
    )
    idp_id: StrictInt = Field(
        ...,
        gt=0,
        description="Identity provider ID being linked",
    )
    created_at: datetime = Field(..., description="Token creation timestamp")
    expires_at: datetime = Field(..., description="Token expiration timestamp")
    used: StrictBool = Field(default=False, description="Token usage flag")
    ip_address: StrictStr | None = Field(
        None,
        max_length=45,
        description="Client IP address",
    )

    model_config = ConfigDict(strict=True)


class IdpLinkTokenRequest(BaseModel):
    """Schema for requesting an IdP link token with step-up verification.

    Linking an identity provider is a sensitive operation that enables
    persistent authentication without local password verification.
    It must be gated by step-up verification: the caller MUST supply
    ``current_password``, and an MFA code when MFA is enabled.

    For SSO-only accounts (no local password set), the password field
    may be omitted and the password check is skipped.

    Attributes:
        current_password: Caller's existing password (step-up verification).
            Required when the account has a local password; may be omitted
            for SSO-only accounts.
        mfa_code: TOTP or backup code, required when MFA is enabled on
            the account.
    """

    current_password: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=250,
        description=("Current password (step-up verification). Required when the account has a local password."),
    )
    mfa_code: StrictStr | None = Field(
        default=None,
        max_length=32,
        description="TOTP or backup code, required when MFA is enabled",
    )

    model_config = ConfigDict(strict=True)


class IdpLinkTokenResponse(BaseModel):
    """Schema for IdP link token response."""

    token: StrictStr = Field(..., description="One-time link token")
    expires_at: datetime = Field(..., description="Token expiration timestamp")

    model_config = ConfigDict(from_attributes=True, strict=True)
