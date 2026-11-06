"""User API key schemas."""

from datetime import UTC, datetime

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    field_validator,
)

import core.pagination as core_pagination
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.utils as api_keys_utils
import modules.auth.identity_providers.schema as idp_schema


class UserApiKeyCreate(BaseModel):
    """Schema for creating a new API key.

    API-key creation is a sensitive, persistent grant of
    account access — it must be gated by step-up
    verification. The caller MUST supply ``current_password``,
    and an MFA code when MFA is enabled on the account.

    An account without a local password (it signs in through an
    identity provider) proves a fresh sign-in with a linked provider
    instead: ``idp_reauth`` carries the ticket from
    ``POST /profile/identity-providers/{idp_id}/step-up``.

    Attributes:
        name: User-friendly label for the key.
        scopes: List containing the supported API key scope.
        expires_at: Optional expiration datetime, at most the server's maximum API key lifetime from now. When
            omitted the key expires at that maximum.
        current_password: Caller's existing password
            (step-up verification). Required when the account
            has a local password.
        mfa_code: TOTP or backup code, required when MFA
            is enabled on the account.
        idp_reauth: Proof of a fresh identity-provider sign-in. Required
            when the account has no local password.
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
    expires_at: AwareDatetime | None = Field(
        None,
        description=(
            "Optional expiration instant with a UTC offset, at most the server's maximum API key lifetime from now. "
            "When omitted the key expires at that maximum."
        ),
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
        """Validate API keys only grant activity upload access.

        Args:
            v: List of scope strings to validate.

        Returns:
            Validated list of scope strings.

        Raises:
            ValueError: If any scope is not supported.
        """
        unsupported = set(v) - api_keys_constants.SUPPORTED_API_KEY_SCOPES
        if unsupported:
            raise ValueError(
                f"Unsupported API key scopes: {', '.join(sorted(unsupported))}. "
                f"Valid scopes: {', '.join(sorted(api_keys_constants.SUPPORTED_API_KEY_SCOPES))}"
            )
        return v

    @field_validator("expires_at")
    @classmethod
    def expires_at_must_be_future(cls, v: AwareDatetime | None) -> datetime | None:
        """Validate the expiry is in the future.

        Args:
            v: Expiration instant, or None to take the server's maximum lifetime.

        Returns:
            The expiration in UTC, or None.

        Raises:
            ValueError: If the expiration is not after the current time.
        """
        if v is None:
            return None
        expires_at = v.astimezone(UTC)
        if expires_at <= datetime.now(UTC):
            raise ValueError("expires_at must be in the future")
        return expires_at

    idp_reauth: idp_schema.IdpReauthProof | None = Field(
        default=None,
        description="Fresh identity-provider sign-in, required when the account has no local password",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UserApiKeyRead(BaseModel):
    """API key read schema for list/detail responses.

    Never exposes the raw key or its hash. Safe to
    return in all authenticated GET responses.

    Attributes:
        id: Unique key identifier (UUID).
        user_id: Owner's user ID.
        name: User-friendly label.
        key_prefix: First 8 chars of the random part.
        scopes: Granted scopes.
        expires_at: Expiration timestamp.
        last_used_at: Last successful use timestamp.
        created_at: Key creation timestamp.
        is_active: Whether the key is currently active.
    """

    id: StrictStr = Field(..., description="Unique key identifier (UUID)")
    user_id: int = Field(..., ge=1, description="Owner's user ID")
    name: StrictStr = Field(..., description="User-friendly label")
    key_prefix: StrictStr = Field(..., description="First 8 chars of the random part")
    scopes: list[StrictStr] = Field(..., description="Granted scopes")
    expires_at: datetime = Field(..., description="Expiration timestamp")
    last_used_at: datetime | None = Field(None, description="Last successful use timestamp")
    created_at: datetime = Field(..., description="Key creation timestamp")
    is_active: StrictBool = Field(..., description="Whether the key is currently active")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("scopes", mode="before")
    @classmethod
    def decode_stored_scopes(cls, v: object) -> object:
        """Decode the JSON text the scopes are stored as.

        Args:
            v: The stored JSON text, or an already-decoded list.

        Returns:
            The list of scopes.
        """
        return api_keys_utils.json_to_scopes(v) if isinstance(v, str) else v


class UserApiKeyCreatedRead(UserApiKeyRead):
    """API key creation response schema.

    Extends UserApiKeyRead with the raw key, returned
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


#: One page of a user's API keys.
UserApiKeyPage = core_pagination.Page[UserApiKeyRead]
