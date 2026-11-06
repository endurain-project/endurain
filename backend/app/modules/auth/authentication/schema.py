"""Pydantic schemas for the authentication module."""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StrictInt,
    StrictStr,
    Tag,
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
        mfa_challenge: The challenge the password step returned for this login.
        mfa_code: Either a 6-digit TOTP code or a backup code.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    mfa_challenge: StrictStr = Field(..., min_length=43, max_length=64)
    mfa_code: StrictStr = Field(
        ...,
        pattern=r"^([0-9]{6}|[A-Z0-9]{4}-[A-Z0-9]{4})$",
    )


class PasswordChangeLoginRequest(BaseModel):
    """Schema for the password-change step of a sign-in.

    Attributes:
        password_change_challenge: The challenge the sign-in returned for this login.
        password: The new password; the account's password policy applies.
    """

    model_config = ConfigDict(extra="forbid")

    password_change_challenge: StrictStr = Field(..., min_length=43, max_length=64)
    password: StrictStr = Field(..., min_length=8, max_length=256)


class MFARequiredRead(BaseModel):
    """Sign-in answer: a second factor must be verified next.

    Attributes:
        next_step: Always ``mfa``; the client sends the MFA code to ``/auth/mfa/verify``.
        mfa_challenge: The challenge the MFA step must send back; it names this login.
    """

    model_config = ConfigDict(extra="forbid")

    next_step: Literal["mfa"]
    mfa_challenge: StrictStr


class PasswordChangeRequiredRead(BaseModel):
    """Sign-in answer: the account's password was set by an administrator and must be replaced next.

    Attributes:
        next_step: Always ``password_change``; the client sends the new password to ``/auth/password-change``.
        password_change_challenge: The challenge the password-change step must send back; it names this login.
    """

    model_config = ConfigDict(extra="forbid")

    next_step: Literal["password_change"]
    password_change_challenge: StrictStr


class MobileSessionRead(BaseModel):
    """Sign-in answer for a mobile client using PKCE: a session to exchange for tokens.

    Attributes:
        next_step: Always ``exchange``; the client exchanges the session at ``/public/idp/session/{session_id}/tokens``.
        session_id: Session identifier for token exchange.
        device_id: The device id the app keeps and sends as ``X-Device-Id`` on later sign-ins.
    """

    model_config = ConfigDict(extra="forbid")

    next_step: Literal["exchange"]
    session_id: StrictStr
    device_id: StrictStr | None = None


class TokenWebRead(BaseModel):
    """Token response payload for web clients.

    Attributes:
        next_step: Always ``tokens``; the client is signed in.
        session_id: Session identifier.
        access_token: Bearer access token.
        csrf_token: CSRF token bound to the session.
        token_type: Always ``bearer``.
        expires_in: Seconds until the access token expires.
        refresh_token_expires_in: Seconds until the refresh token expires.
    """

    model_config = ConfigDict(extra="forbid")

    next_step: Literal["tokens"]
    session_id: StrictStr
    access_token: StrictStr
    csrf_token: StrictStr
    token_type: Literal["bearer"] = "bearer"
    expires_in: StrictInt
    refresh_token_expires_in: StrictInt


class TokenMobileRead(BaseModel):
    """Token response payload for mobile clients.

    Attributes:
        next_step: Always ``tokens``; the client is signed in.
        session_id: Session identifier.
        access_token: Bearer access token.
        refresh_token: Refresh token.
        token_type: Always ``bearer``.
        expires_in: Seconds until the access token expires.
        refresh_token_expires_in: Seconds until the refresh token expires.
        device_id: The device id the app keeps and sends as ``X-Device-Id`` on later sign-ins; set by a sign-in, null
            on a refresh.
    """

    model_config = ConfigDict(extra="forbid")

    next_step: Literal["tokens"]
    session_id: StrictStr
    access_token: StrictStr
    refresh_token: StrictStr
    token_type: Literal["bearer"] = "bearer"
    expires_in: StrictInt
    refresh_token_expires_in: StrictInt
    device_id: StrictStr | None = None


class TokenExchangeRequest(BaseModel):
    """Request schema for mobile PKCE token exchange.

    After OAuth callback completes, mobile clients exchange the session_id
    for actual JWT tokens by proving they possess the code_verifier that
    matches the code_challenge sent during login initiation.

    Attributes:
        code_verifier (str): PKCE code verifier (43-128 chars, base64url).
            Must hash to the code_challenge stored in OAuth state.
        mfa_code (str | None): TOTP or backup code. Required when the session
            came from an identity provider and the account has MFA enabled.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code_verifier: StrictStr = Field(
        ...,
        min_length=43,
        max_length=128,
        description="PKCE code verifier (base64url, 43-128 chars)",
    )
    mfa_code: StrictStr | None = Field(
        default=None,
        pattern=r"^([0-9]{6}|[A-Z0-9]{4}-[A-Z0-9]{4})$",
        description="MFA code, required for an identity-provider session of an account with MFA enabled",
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
        device_id (str | None): The device id a mobile app keeps and sends as ``X-Device-Id`` on later sign-ins; set
            by the exchange of an identity-provider sign-in, null otherwise.
    """

    session_id: StrictStr = Field(..., description="Session identifier")
    access_token: StrictStr = Field(..., description="JWT access token")
    refresh_token: StrictStr | None = Field(default=None, description="JWT refresh token (mobile only)")
    csrf_token: StrictStr | None = Field(default=None, description="CSRF protection token (web only)")
    expires_in: StrictInt = Field(default=900, description="Access token lifetime in seconds")
    refresh_token_expires_in: StrictInt = Field(default=604800, description="Refresh token lifetime in seconds")
    token_type: StrictStr = Field(default="Bearer", description="Token type")
    device_id: StrictStr | None = Field(
        default=None, description="Device id a mobile app keeps and sends as X-Device-Id (identity-provider sign-in)"
    )


@dataclass(frozen=True)
class RefreshCookie:
    """Refresh token a web client receives as an ``HttpOnly`` cookie.

    Attributes:
        value: The refresh token.
        expires_at: When the cookie and the token expire.
    """

    value: str
    expires_at: datetime


def _next_step(body: object) -> str | None:
    """Return the ``next_step`` of a sign-in body, whether it is a model or the dict it was parsed from."""
    if isinstance(body, dict):
        return body.get("next_step")
    return getattr(body, "next_step", None)


#: The token body of a password login or a refresh, by client type.
type TokenRead = TokenWebRead | TokenMobileRead

# The two token bodies share the ``tokens`` step, which a pydantic field discriminator cannot map to two models, so
# the union is tagged by a function and the ``tokens`` step holds both.
_Mfa = Annotated[MFARequiredRead, Tag("mfa")]
_PasswordChange = Annotated[PasswordChangeRequiredRead, Tag("password_change")]
_Exchange = Annotated[MobileSessionRead, Tag("exchange")]
_Tokens = Annotated[TokenWebRead | TokenMobileRead, Tag("tokens")]

#: What ends a sign-in with a session: tokens, or for a mobile PKCE client a session to exchange.
FinishedLoginRead = Annotated[_Exchange | _Tokens, Discriminator(_next_step)]

#: The answer of ``/auth/mfa/verify``: a password change, a session to exchange, or the tokens.
MFAVerifyRead = Annotated[_PasswordChange | _Exchange | _Tokens, Discriminator(_next_step)]

#: The answer of ``/auth/login``, told apart by ``next_step``.
LoginRead = Annotated[_Mfa | _PasswordChange | _Exchange | _Tokens, Discriminator(_next_step)]


@dataclass(frozen=True)
class AuthOutcome[BodyT: BaseModel]:
    """Result of an authentication workflow, before the transport delivers it.

    Attributes:
        body: Response body for the client.
        refresh_cookie: Cookie the router sets for a web client; ``None`` when the refresh token is not delivered
            as a cookie.
        device_id: Device id the router keeps in the browser's device cookie after a web sign-in; ``None`` for any
            other outcome, a mobile client's device id travelling in its body.
    """

    body: BodyT
    refresh_cookie: RefreshCookie | None = None
    device_id: str | None = None
