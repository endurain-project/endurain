"""Pydantic schemas for the authentication module."""

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)

import modules.auth.computation as auth_computation
import modules.auth.credentials.contracts as credentials_contracts


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
    password: StrictStr = Field(..., max_length=credentials_contracts.PASSWORD_MAX_LENGTH)


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
    """Sign-in answer for a mobile client: a session to exchange for tokens with its PKCE verifier.

    Attributes:
        next_step: Always ``exchange``; the client exchanges the session at ``/auth/sessions/{session_id}/tokens``.
        session_id: Session identifier for token exchange.
        device_id: The device id the app keeps and sends as ``X-Device-Id`` on later sign-ins.
    """

    model_config = ConfigDict(extra="forbid")

    next_step: Literal["exchange"]
    session_id: StrictStr
    device_id: StrictStr | None = None


class LogoutRead(BaseModel):
    """Sign-out answer: where to end the session at the identity provider, when the session signed in through one.

    Attributes:
        idp_logout_url: The identity provider's end-session URL, carrying the ID token as a hint, or None when the
            session did not sign in through a provider, the provider has no end-session endpoint, or the URL could
            not be built. A web client sends the browser there; a mobile client may open it in the system browser.
    """

    model_config = ConfigDict(extra="forbid")

    idp_logout_url: StrictStr | None = Field(
        description=(
            "The identity provider's end-session URL, or null when there is none. It carries the ID token, so a "
            "client uses it once and does not store it."
        )
    )


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
        device_id: The device id the app keeps and sends as ``X-Device-Id`` on later sign-ins; set by the exchange of a
            sign-in, null on a refresh.
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


class RefreshTokenRequest(BaseModel):
    """Request body that carries a mobile client's refresh token (RFC 6749 section 6, RFC 7009).

    Attributes:
        refresh_token (str): The refresh token the client holds.
    """

    model_config = ConfigDict(extra="forbid")

    refresh_token: StrictStr = Field(..., description="The refresh token of a mobile client")


class TokenExchangeRequest(BaseModel):
    """Request schema for mobile PKCE token exchange.

    After OAuth callback completes, mobile clients exchange the session_id
    for actual JWT tokens by proving they possess the code_verifier that
    matches the code_challenge sent during login initiation.

    Attributes:
        code_verifier (str): PKCE code verifier (43-128 chars of the RFC 7636 unreserved set).
            Must hash to the code_challenge stored in OAuth state.
        mfa_code (str | None): TOTP or backup code. Required when the session
            came from an identity provider and the account has MFA enabled.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    code_verifier: StrictStr = Field(
        ...,
        min_length=43,
        max_length=128,
        description="PKCE code verifier (43-128 characters: A-Z, a-z, 0-9, '-', '.', '_', '~')",
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
        if not auth_computation.PKCE_VERIFIER_PATTERN.match(v):
            raise ValueError(auth_computation.PKCE_VERIFIER_CHARSET_MESSAGE)
        return v


@dataclass(frozen=True)
class RefreshCookie:
    """Refresh token a web client receives as an ``HttpOnly`` cookie.

    Attributes:
        value: The refresh token.
        expires_at: When the cookie and the token expire.
    """

    value: str
    expires_at: datetime


#: The token body of a refresh or a token exchange: a web client's or a mobile client's, by its client type.
type TokenRead = TokenWebRead | TokenMobileRead

#: What ends a sign-in with a session: the tokens of a web client, or for a mobile client a session to exchange.
FinishedLoginRead = Annotated[MobileSessionRead | TokenWebRead, Field(discriminator="next_step")]

#: The answer of ``/auth/mfa/verify``: a password change, a session to exchange, or the tokens of a web client.
MFAVerifyRead = Annotated[
    PasswordChangeRequiredRead | MobileSessionRead | TokenWebRead, Field(discriminator="next_step")
]

#: The answer of ``/auth/login``, told apart by ``next_step``.
LoginRead = Annotated[
    MFARequiredRead | PasswordChangeRequiredRead | MobileSessionRead | TokenWebRead, Field(discriminator="next_step")
]


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
