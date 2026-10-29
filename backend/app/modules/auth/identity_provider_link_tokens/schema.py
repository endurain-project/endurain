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

import modules.auth.identity_providers.schema as idp_schema


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

    model_config = ConfigDict(from_attributes=True, strict=True)


class IdpLinkTokenRead(IdpLinkTokenCreate):
    """Persisted one-time link-token record."""


class IdpLinkTokenRequest(BaseModel):
    """Schema for requesting an IdP link token with step-up verification.

    Linking an identity provider is a sensitive operation that enables
    persistent authentication without local password verification.
    It must be gated by step-up verification: the caller MUST supply
    ``current_password``, and an MFA code when MFA is enabled.

    An account without a local password (it signs in through an identity
    provider) proves a fresh sign-in with a linked provider instead, in
    ``idp_reauth``.

    Attributes:
        current_password: Caller's existing password (step-up verification).
            Required when the account has a local password.
        mfa_code: TOTP or backup code, required when MFA is enabled on
            the account.
        idp_reauth: Proof of a fresh identity-provider sign-in. Required
            when the account has no local password.
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

    idp_reauth: idp_schema.IdpReauthProof | None = Field(
        default=None,
        description="Fresh identity-provider sign-in, required when the account has no local password",
    )

    model_config = ConfigDict(strict=True)


class IdentityProviderLinkTokenRead(BaseModel):
    """Schema for IdP link token response."""

    token: StrictStr = Field(..., description="One-time link token")
    expires_at: datetime = Field(..., description="Token expiration timestamp")

    model_config = ConfigDict(from_attributes=True, strict=True)
