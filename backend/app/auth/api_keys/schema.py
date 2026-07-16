"""User API key schemas."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
)

import auth.api_keys.utils as api_keys_utils


class UsersApiKeyCreate(BaseModel):
    """
    Schema for creating a new API key.

    API-key creation is a sensitive, persistent grant of
    account access — it must be gated by step-up
    verification. The caller MUST supply ``current_password``,
    and an MFA code when MFA is enabled on the account.

    For SSO-only accounts (no local password set), the password
    field may be omitted and the password check is skipped — see
    :func:`auth._internal.services.step_up_service.verify_step_up_credentials`
    and ``docs/developer-guide/auth-boundary.md`` for the rationale
    and the tracked SSO-only step-up gap.

    Attributes:
        name: User-friendly label for the key.
        scopes: List containing the supported API key scope.
        expires_at: Optional expiration datetime.
            None means the key never expires.
        current_password: Caller's existing password
            (step-up verification). Required when the account
            has a local password; may be omitted for SSO-only
            accounts.
        mfa_code: TOTP or backup code, required when MFA
            is enabled on the account.
    """

    name: StrictStr = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User-friendly label for the key",
    )
    scopes: list[StrictStr] = Field(
        ...,
        min_length=1,
        description="List of scope strings to grant",
    )
    expires_at: datetime | None = Field(
        None,
        description=("Optional expiration datetime. None means the key never expires."),
    )
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

    @field_validator("scopes")
    @classmethod
    def scopes_must_be_valid(cls, v: list[str]) -> list[str]:
        """
        Validate API keys only grant activity upload access.

        Args:
            v: List of scope strings to validate.

        Returns:
            Validated list of scope strings.

        Raises:
            ValueError: If any scope is not supported.
        """
        unsupported = set(v) - api_keys_utils.SUPPORTED_API_KEY_SCOPES
        if unsupported:
            raise ValueError(
                f"Unsupported API key scopes: {unsupported}. Valid scopes: {api_keys_utils.SUPPORTED_API_KEY_SCOPES}"
            )
        return v

    model_config = ConfigDict(from_attributes=True)


class UsersApiKeyRead(BaseModel):
    """
    API key read schema for list/detail responses.

    Never exposes the raw key or its hash. Safe to
    return in all authenticated GET responses.

    Attributes:
        id: Unique key identifier (UUID).
        user_id: Owner's user ID.
        name: User-friendly label.
        key_prefix: First 8 chars of the random part.
        scopes: JSON-encoded list of granted scopes.
        expires_at: Optional expiration timestamp.
        last_used_at: Last successful use timestamp.
        created_at: Key creation timestamp.
        is_active: Whether the key is currently active.
    """

    id: StrictStr = Field(..., description="Unique key identifier (UUID)")
    user_id: int = Field(..., ge=1, description="Owner's user ID")
    name: StrictStr = Field(..., description="User-friendly label")
    key_prefix: StrictStr = Field(..., description="First 8 chars of the random part")
    scopes: StrictStr = Field(..., description="JSON-encoded list of granted scopes")
    expires_at: datetime | None = Field(None, description="Optional expiration timestamp")
    last_used_at: datetime | None = Field(None, description="Last successful use timestamp")
    created_at: datetime = Field(..., description="Key creation timestamp")
    is_active: StrictBool = Field(..., description="Whether the key is currently active")

    model_config = ConfigDict(from_attributes=True)


class UsersApiKeyCreated(UsersApiKeyRead):
    """
    API key creation response schema.

    Extends UsersApiKeyRead with the raw key, returned
    only once at creation time. The raw key is never
    stored and cannot be retrieved again.

    Attributes:
        key: The full raw API key. Show to the user
            once and discard.
    """

    key: StrictStr = Field(
        ...,
        description=("Full raw API key. Shown once at creation only — store it securely."),
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )
