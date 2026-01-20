"""User session schemas."""

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    StrictStr,
    StrictInt,
    StrictBool,
)
from datetime import datetime


class UsersSessionsBase(BaseModel):
    """
    Base user session schema with safe fields.

    Attributes:
        id: Unique session identifier.
        ip_address: Client IP address.
        device_type: Device type.
        operating_system: Operating system name.
        operating_system_version: OS version string.
        browser: Browser name.
        browser_version: Browser version string.
        created_at: Session creation timestamp.
        last_activity_at: Last activity timestamp.
        expires_at: Session expiration timestamp.
    """

    id: StrictStr = Field(..., description="Unique session identifier")
    ip_address: StrictStr = Field(..., max_length=45, description="Client IP address")
    device_type: StrictStr = Field(..., max_length=45, description="Device type")
    operating_system: StrictStr = Field(
        ..., max_length=45, description="Operating system"
    )
    operating_system_version: StrictStr = Field(
        ..., max_length=45, description="OS version"
    )
    browser: StrictStr = Field(..., max_length=45, description="Browser name")
    browser_version: StrictStr = Field(
        ..., max_length=45, description="Browser version"
    )
    created_at: datetime = Field(..., description="Session creation timestamp")
    last_activity_at: datetime = Field(..., description="Last activity timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")

    model_config = ConfigDict(from_attributes=True)


class UsersSessionsRead(UsersSessionsBase):
    """
    User session read schema for API responses.

    Extends base with user_id. Excludes sensitive fields
    like refresh_token and csrf_token_hash.
    """

    user_id: StrictInt = Field(..., ge=1, description="User ID that owns this session")


class UsersSessionsInternal(UsersSessionsBase):
    """
    Internal user session schema with all fields.

    Used for CRUD operations. Includes sensitive fields like
    refresh_token and csrf_token_hash that should never be
    exposed in API responses.

    Attributes:
        user_id: User ID that owns this session.
        refresh_token: Hashed session refresh token.
        oauth_state_id: Link to OAuth state for PKCE.
        tokens_exchanged: Prevents duplicate mobile token
            exchange.
        token_family_id: UUID for token family reuse
            detection.
        rotation_count: Number of times refresh token
            rotated.
        last_rotation_at: Timestamp of last token rotation.
        csrf_token_hash: Hashed CSRF token for refresh
            validation.
    """

    user_id: StrictInt = Field(..., ge=1, description="User ID that owns this session")
    refresh_token: StrictStr | None = Field(
        None, description="Hashed session refresh token"
    )
    oauth_state_id: StrictStr | None = Field(
        None,
        max_length=64,
        description="Link to OAuth state for PKCE validation",
    )
    tokens_exchanged: StrictBool = Field(
        default=False,
        description="Prevents duplicate token exchange for " "mobile",
    )
    token_family_id: StrictStr = Field(
        ...,
        description="UUID identifying token family for reuse " "detection",
    )
    rotation_count: StrictInt = Field(
        default=0,
        ge=0,
        description="Number of times refresh token has been " "rotated",
    )
    last_rotation_at: datetime | None = Field(
        None, description="Timestamp of last token rotation"
    )
    csrf_token_hash: StrictStr | None = Field(
        None,
        max_length=255,
        description="Hashed CSRF token for refresh " "validation",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
