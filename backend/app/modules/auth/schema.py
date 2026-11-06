"""Request shapes shared by the auth packages and the modules that ask for a step-up."""

from pydantic import BaseModel, ConfigDict, Field, StrictStr


class IdpReauthProof(BaseModel):
    """Proof that a password-less account signed in again with its identity provider.

    The provider's callback hands the ticket to the browser that started the step-up; that browser also holds
    the PKCE verifier whose challenge the ticket records, so a ticket alone cannot be redeemed.

    Attributes:
        ticket: The single-use step-up ticket.
        code_verifier: The PKCE verifier the step-up was started with.
    """

    ticket: StrictStr = Field(..., min_length=43, max_length=64, description="Single-use step-up ticket")
    code_verifier: StrictStr = Field(
        ..., min_length=43, max_length=128, description="PKCE verifier the step-up was started with"
    )

    model_config = ConfigDict(extra="forbid")


class StepUpVerification(BaseModel):
    """Generic step-up verification payload.

    Used by sensitive account-level operations (API key
    creation, MFA backup-code regeneration, etc.) to require
    fresh proof of identity beyond a valid access token.

    An account without a local password (it signs in through an
    identity provider) proves a fresh sign-in with a linked provider
    instead: ``idp_reauth`` carries the ticket from
    ``POST /profile/identity-providers/{idp_id}/step-up``.

    Attributes:
        current_password: Caller's existing password. Required
            when the account has a local password.
        mfa_code: TOTP or backup code, required when MFA is
            enabled on the account.
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

    idp_reauth: IdpReauthProof | None = Field(
        default=None,
        description="Fresh identity-provider sign-in, required when the account has no local password",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )
