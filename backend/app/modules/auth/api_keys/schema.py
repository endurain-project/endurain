"""User API key schemas."""

import uuid
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
import modules.auth.schema as auth_schema


class UserApiKeyCreate(BaseModel):
    """Schema for creating a new API key.

    API-key creation is a sensitive, persistent grant of
    account access — it must be gated by step-up
    verification, carried in ``step_up``.

    Attributes:
        name: User-friendly label for the key.
        scopes: The scopes to grant, each one an API key may hold.
        expires_at: Optional expiration datetime, at most the server's maximum API key lifetime from now. When
            omitted the key expires at that maximum.
        step_up: The caller's step-up verification.
    """

    name: StrictStr = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User-friendly label for the key",
    )
    scopes: list[api_keys_constants.ApiKeyScope] = Field(
        ...,
        min_length=1,
        description="Scopes to grant: the account's own data, never its security, export, provider links or administration",
    )
    expires_at: AwareDatetime | None = Field(
        None,
        description=(
            "Optional expiration instant with a UTC offset, at most the server's maximum API key lifetime from now. "
            "When omitted the key expires at that maximum."
        ),
    )
    step_up: auth_schema.StepUpVerification = Field(
        ..., description="Step-up verification, required to create an API key"
    )

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

    id: uuid.UUID = Field(..., description="Unique key identifier (UUID)")
    user_id: uuid.UUID = Field(..., description="Owner's user ID")
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
