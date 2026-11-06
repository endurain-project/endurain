"""Pydantic schemas for MFA operations (owned by auth)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
)

import modules.auth.schema as auth_schema


class MFARequest(BaseModel):
    """Request model for MFA verification.

    Attributes:
        mfa_code: The MFA code to verify (6-digit TOTP or
            9-char backup code).
    """

    mfa_code: StrictStr = Field(
        ...,
        min_length=6,
        max_length=9,
        description="MFA code (6-digit TOTP or XXXX-XXXX)",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    @field_validator("mfa_code")
    @classmethod
    def validate_mfa_code_format(cls, v: str) -> str:
        """Validate MFA code format.

        Args:
            v: MFA code to validate.

        Returns:
            Validated MFA code.

        Raises:
            ValueError: If code format is invalid.
        """
        normalized = v.strip().upper()
        # 6-digit TOTP
        if len(normalized) == 6 and normalized.isascii() and normalized.isdecimal():
            return normalized
        # 9-char backup code (XXXX-XXXX)
        if len(normalized) == 9 and normalized[4] == "-":
            return normalized
        raise ValueError("MFA code must be 6-digit TOTP or XXXX-XXXX")


class MFASetupRequest(BaseModel):
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
        step_up: The caller's step-up verification.
    """

    mfa_code: StrictStr = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^[0-9]{6}$",
        description="6-digit TOTP code",
    )
    step_up: auth_schema.StepUpVerification = Field(..., description="Step-up verification, required to enable MFA")

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


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
