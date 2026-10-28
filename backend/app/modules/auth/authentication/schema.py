"""Pydantic schemas for the authentication module."""

import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
)


class LoginRequest(BaseModel):
    """Schema for login requests containing username and password.

    Attributes:
        username: Username of the user.
        password: User password.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: StrictStr = Field(..., min_length=1, max_length=250)
    password: StrictStr = Field(..., min_length=8)


class MFALoginRequest(BaseModel):
    """Schema for MFA login requests.

    Attributes:
        username: Username of the user attempting to log in.
        mfa_code: Either a 6-digit TOTP code or a backup code.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    username: StrictStr = Field(..., min_length=1, max_length=250)
    mfa_code: StrictStr = Field(
        ...,
        pattern=r"^(\d{6}|[A-Z0-9]{4}-[A-Z0-9]{4})$",
    )


class MFARequiredRead(BaseModel):
    """Response indicating MFA verification is required.

    Attributes:
        mfa_required: Indicates whether MFA is required.
        username: Username for which MFA is required.
        message: Message describing the requirement.
    """

    model_config = ConfigDict(extra="forbid")

    mfa_required: StrictBool = True
    username: StrictStr
    message: StrictStr = "MFA verification required"


class MobileSessionRead(BaseModel):
    """Response for mobile password login with PKCE exchange flow.

    Attributes:
        session_id: Session identifier for token exchange.
        mfa_required: Whether MFA is required.
        message: Instructions for the client on next steps.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: StrictStr
    mfa_required: StrictBool = False
    message: StrictStr = "Complete authentication by exchanging tokens at /public/idp/session/{session_id}/tokens"


class TokenWebRead(BaseModel):
    """Token response payload for web clients.

    Attributes:
        session_id: Session identifier.
        access_token: Bearer access token.
        csrf_token: CSRF token bound to the session.
        token_type: Always ``bearer``.
        expires_in: Seconds until the access token expires.
        refresh_token_expires_in: Seconds until the refresh token expires.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: StrictStr
    access_token: StrictStr
    csrf_token: StrictStr
    token_type: Literal["bearer"] = "bearer"
    expires_in: StrictInt
    refresh_token_expires_in: StrictInt


class TokenMobileRead(BaseModel):
    """Token response payload for mobile clients.

    Attributes:
        session_id: Session identifier.
        access_token: Bearer access token.
        refresh_token: Refresh token.
        token_type: Always ``bearer``.
        expires_in: Seconds until the access token expires.
        refresh_token_expires_in: Seconds until the refresh token expires.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: StrictStr
    access_token: StrictStr
    refresh_token: StrictStr
    token_type: Literal["bearer"] = "bearer"
    expires_in: StrictInt
    refresh_token_expires_in: StrictInt


class LogoutRead(BaseModel):
    """Response payload returned by the logout endpoint.

    Attributes:
        message: Human-readable confirmation message.
    """

    model_config = ConfigDict(extra="forbid")

    message: StrictStr


class TokenExchangeRequest(BaseModel):
    """Request schema for mobile PKCE token exchange.

    After OAuth callback completes, mobile clients exchange the session_id
    for actual JWT tokens by proving they possess the code_verifier that
    matches the code_challenge sent during login initiation.

    Attributes:
        code_verifier (str): PKCE code verifier (43-128 chars, base64url).
            Must hash to the code_challenge stored in OAuth state.
    """

    code_verifier: StrictStr = Field(
        ...,
        min_length=43,
        max_length=128,
        description="PKCE code verifier (base64url, 43-128 chars)",
    )

    @field_validator("code_verifier")
    @classmethod
    def validate_code_verifier(cls, v: str) -> str:
        """Validate PKCE code_verifier format according to RFC 7636.

        Args:
            v (str): The code verifier string.

        Returns:
            str: The validated code verifier.

        Raises:
            ValueError: If format is invalid (wrong length or characters).
        """
        if not re.match(r"^[A-Za-z0-9_-]+$", v):
            raise ValueError("code_verifier must be valid base64url")
        return v


class TokenExchangeRead(BaseModel):
    """Response schema for successful PKCE token exchange.

    Returns the actual JWT tokens that clients need for API access.
    Response format varies by client type:
    - Web clients: access_token, csrf_token (refresh_token in httpOnly cookie)
    - Mobile clients: access_token, refresh_token (no CSRF token)

    Attributes:
        session_id (str): Session identifier.
        access_token (str): JWT access token (15-minute expiry).
        refresh_token (str | None): JWT refresh token (7-day expiry). Only for mobile clients.
        csrf_token (str | None): CSRF protection token. Only for web clients.
        expires_in (int): Access token lifetime in seconds (900 = 15 minutes).
        refresh_token_expires_in (int): Refresh token lifetime in seconds (604800 = 7 days).
        token_type (str): Token type, always "Bearer".
    """

    session_id: StrictStr = Field(..., description="Session identifier")
    access_token: StrictStr = Field(..., description="JWT access token")
    refresh_token: StrictStr | None = Field(default=None, description="JWT refresh token (mobile only)")
    csrf_token: StrictStr | None = Field(default=None, description="CSRF protection token (web only)")
    expires_in: StrictInt = Field(default=900, description="Access token lifetime in seconds")
    refresh_token_expires_in: StrictInt = Field(default=604800, description="Refresh token lifetime in seconds")
    token_type: StrictStr = Field(default="Bearer", description="Token type")
