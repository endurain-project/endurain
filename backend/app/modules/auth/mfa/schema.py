"""Pydantic schemas for MFA operations (owned by auth)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
)

import modules.auth.schema as auth_schema


class MFAChangeRequest(BaseModel):
    """Request model for a change to the second factor, authorised by step-up verification.

    Attributes:
        step_up: The caller's step-up verification.
        revoke_other_sessions: Whether to sign out the user's other sessions after the change.
    """

    step_up: auth_schema.StepUpVerification = Field(
        ..., description="Step-up verification, required to change the second factor"
    )
    revoke_other_sessions: StrictBool = Field(
        default=True,
        description=(
            "After the change, all of the user's other sessions "
            "(keeping the current one) are revoked unless the client sends false."
        ),
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class MFASetupRequest(MFAChangeRequest):
    """Request model for MFA setup verification.

    Enabling MFA binds a TOTP secret — just handed to the caller
    by ``POST /profile/mfa/setup`` — to the account, and issues
    backup codes. A stolen access token alone must not be enough
    to complete this binding (otherwise the attacker enrols their
    own authenticator and locks the legitimate user out), so the
    request is gated by step-up verification, carried in ``step_up``,
    in addition to the freshly enrolled TOTP code.

    Attributes:
        mfa_code: The 6-digit TOTP code generated from the secret
            returned by the setup endpoint, used to confirm the
            authenticator app is correctly enrolled.
    """

    mfa_code: StrictStr = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^[0-9]{6}$",
        description="6-digit TOTP code",
    )


class MFADisableRequest(MFAChangeRequest):
    """Request model for turning MFA off: the step-up verification, with its MFA code, and the session choice."""


class MFABackupCodesRequest(MFAChangeRequest):
    """Request model for issuing new MFA backup codes: the step-up verification and the session choice."""


class MFASetupRead(BaseModel):
    """Response model for MFA setup initialization.

    Attributes:
        secret: The MFA secret key.
        qr_code: Base64-encoded QR code image for setup.
        app_name: Application name for MFA setup.
    """

    secret: StrictStr = Field(
        ...,
        description="TOTP secret key",
    )
    qr_code: StrictStr = Field(
        ...,
        description="Base64-encoded QR code image",
    )
    app_name: StrictStr = Field(
        default="Endurain",
        description="Application name for MFA",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MFAStatusRead(BaseModel):
    """Response model for MFA status.

    Attributes:
        mfa_enabled: Whether MFA is enabled for the user.
    """

    mfa_enabled: StrictBool = Field(
        ...,
        description="Whether MFA is enabled",
    )

    model_config = ConfigDict(
        extra="forbid",
    )


class MFAEnableRead(BaseModel):
    """Response returned after MFA is enabled.

    Attributes:
        message: Confirmation message.
        backup_codes: Newly generated one-time backup codes.
    """

    message: StrictStr
    backup_codes: list[StrictStr]

    model_config = ConfigDict(extra="forbid")
