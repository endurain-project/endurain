"""Pydantic schemas for MFA operations (owned by auth)."""

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
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


class MFADisableRequest(MFARequest):
    """
    Request model for MFA disable verification.

    Disabling MFA is a sensitive, security-reducing operation
    and must be gated by step-up verification: the caller has to
    re-prove possession of the current password in addition to a
    valid MFA code. The password length bounds match the other
    step-up schemas (see ``UsersEditPassword``) — they validate
    the supplied input only and do not impose a policy on the
    stored password.

    For SSO-only accounts (no local password set), the password
    field may be omitted and the password check is skipped — see
    :func:`modules.auth._internal.services.step_up_service.verify_step_up_credentials`
    and ``docs/developer-guide/auth-boundary.md`` for the rationale
    and the tracked SSO-only step-up gap.

    Attributes:
        current_password: Caller's existing password (step-up
            verification). Required when the account has a local
            password; may be omitted for SSO-only accounts.
    """

    current_password: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=250,
        description=("Current password (step-up verification). Required when the account has a local password."),
    )


class MFASetupRequest(BaseModel):
    """
    Request model for MFA setup verification.

    Enabling MFA binds a TOTP secret — just handed to the caller
    by ``POST /profile/mfa/setup`` — to the account, and issues
    backup codes. A stolen access token alone must not be enough
    to complete this binding (otherwise the attacker enrols their
    own authenticator and locks the legitimate user out), so the
    request is gated by step-up verification: the caller must
    re-prove their current password in addition to the freshly
    enrolled TOTP code.

    For SSO-only accounts (no local password set), the password
    field may be omitted and the password check is skipped — see
    :func:`modules.auth._internal.services.step_up_service.verify_step_up_credentials`
    and ``docs/developer-guide/auth-boundary.md`` for the rationale
    and the tracked SSO-only step-up gap.

    Attributes:
        mfa_code: The 6-digit TOTP code generated from the secret
            returned by the setup endpoint, used to confirm the
            authenticator app is correctly enrolled.
        current_password: Caller's existing password (step-up
            verification). Required when the account has a local
            password; may be omitted for SSO-only accounts.
    """

    mfa_code: StrictStr = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit TOTP code",
    )
    current_password: StrictStr | None = Field(
        default=None,
        min_length=1,
        max_length=250,
        description=("Current password (step-up verification). Required when the account has a local password."),
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
