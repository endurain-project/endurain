"""User identity provider Pydantic schemas."""

from datetime import datetime
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
)


class UserIdentityProviderBase(BaseModel):
    """
    Base schema for user identity provider association.

    Attributes:
        user_id: User ID reference.
        idp_id: Identity Provider ID reference.
        idp_subject: Subject/ID from the identity provider.
    """

    user_id: StrictInt = Field(..., ge=1, description="User ID")
    idp_id: StrictInt = Field(..., ge=1, description="Identity Provider ID")
    idp_subject: StrictStr = Field(
        ...,
        max_length=500,
        min_length=1,
        description="Subject/ID from the identity provider",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


class UserIdentityProviderCreate(UserIdentityProviderBase):
    """
    Schema for creating user identity provider links.

    Inherits all attributes from UserIdentityProviderBase.
    Links are created during SSO authentication flow.
    """


class UserIdentityProviderRead(UserIdentityProviderBase):
    """
    Schema for reading user identity provider links.

    Extends base with identifier and timestamp fields.
    Refresh token is excluded for security.

    Attributes:
        id: Unique identifier for the link.
        linked_at: When this IdP was linked.
        last_login: Last login using this IdP.
        idp_access_token_expires_at: Access token expiry.
        idp_refresh_token_updated_at: Refresh token update time.
    """

    id: StrictInt = Field(..., description="Link ID")
    linked_at: datetime = Field(..., description="When linked")
    last_login: datetime | None = Field(
        None,
        description="Last login using this IdP",
    )
    idp_access_token_expires_at: datetime | None = Field(
        None,
        description="Access token expiry",
    )
    idp_refresh_token_updated_at: datetime | None = Field(
        None,
        description="Refresh token update time",
    )


class UserIdentityProviderResponse(UserIdentityProviderRead):
    """
    Response schema with enriched identity provider details.

    Extends Read schema with display fields added by API layer
    for frontend convenience.

    Attributes:
        idp_name: Identity provider name (enriched).
        idp_slug: Identity provider slug (enriched).
        idp_icon: Identity provider icon (enriched).
        idp_provider_type: Provider type (enriched).
    """

    idp_name: StrictStr | None = Field(
        None,
        description="Identity provider name",
    )
    idp_slug: StrictStr | None = Field(
        None,
        description="Identity provider slug",
    )
    idp_icon: StrictStr | None = Field(
        None,
        description="Identity provider icon",
    )
    idp_provider_type: StrictStr | None = Field(
        None,
        description="Provider type",
    )


class UserIdentityProviderTokenUpdate(BaseModel):
    """
    Internal schema for updating IdP token data.

    Used only by service layer, never exposed via API.
    Refresh token must be encrypted before storage.

    Attributes:
        idp_refresh_token: Encrypted refresh token.
        idp_access_token_expires_at: Access token expiry.
        idp_refresh_token_updated_at: Refresh token update time.
    """

    idp_refresh_token: StrictStr | None = Field(
        None,
        description="Encrypted refresh token",
    )
    idp_access_token_expires_at: datetime | None = Field(
        None,
        description="Access token expiry",
    )
    idp_refresh_token_updated_at: datetime | None = Field(
        None,
        description="Refresh token update time",
    )

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )
