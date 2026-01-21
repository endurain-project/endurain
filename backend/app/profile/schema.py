"""Profile Pydantic schemas for MFA and profile operations."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    StrictBool,
    field_validator,
)


class MFARequest(BaseModel):
    """
    Request model for MFA verification.

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
        """
        Validate MFA code format.

        Args:
            v: MFA code to validate.

        Returns:
            Validated MFA code.

        Raises:
            ValueError: If code format is invalid.
        """
        normalized = v.strip().upper()
        # 6-digit TOTP
        if len(normalized) == 6 and normalized.isdigit():
            return normalized
        # 9-char backup code (XXXX-XXXX)
        if len(normalized) == 9 and normalized[4] == "-":
            return normalized
        raise ValueError("MFA code must be 6-digit TOTP or XXXX-XXXX")


class MFASetupRequest(BaseModel):
    """
    Request model for MFA setup verification.

    Attributes:
        mfa_code: The 6-digit MFA code to verify during
            setup.
    """

    mfa_code: StrictStr = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit TOTP code",
    )

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class MFASetupResponse(BaseModel):
    """
    Response model for MFA setup initialization.

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


class MFAStatusResponse(BaseModel):
    """
    Response model for MFA status.

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
