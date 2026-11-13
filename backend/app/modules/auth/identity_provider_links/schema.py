"""User identity provider Pydantic schemas."""

import uuid
from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
)

import core.pagination as core_pagination


class UserIdentityProviderBase(BaseModel):
    """Base schema for users identity provider association.

    Attributes:
        user_id: User ID reference.
        idp_id: Identity Provider ID reference.
        idp_subject: Subject/ID from the identity provider.
    """

    user_id: uuid.UUID = Field(..., description="User ID")
    idp_id: uuid.UUID = Field(..., description="Identity Provider ID")
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
    """Schema for creating user identity provider links.

    Inherits all attributes from UserIdentityProviderBase.
    Links are created during SSO authentication flow.
    """


class UserIdentityProviderRead(UserIdentityProviderBase):
    """Schema for reading user identity provider links.

    Extends base with identifier and timestamp fields.

    Attributes:
        id: Unique identifier for the link.
        linked_at: When this IdP was linked.
        last_login: Last login using this IdP.
    """

    id: uuid.UUID = Field(..., description="Link ID")
    linked_at: datetime = Field(..., description="When linked")
    last_login: datetime | None = Field(
        default=None,
        description="Last login using this IdP",
    )


class IdentityProviderLinkRead(UserIdentityProviderRead):
    """Response schema with enriched identity provider details.

    Extends Read schema with display fields added by API layer
    for frontend convenience.

    Attributes:
        idp_name: Identity provider name (enriched).
        idp_slug: Identity provider slug (enriched).
        idp_icon: Identity provider icon (enriched).
        idp_icon_uploaded: Whether an uploaded icon is shown instead of the icon (enriched).
        idp_provider_type: Provider type (enriched).
    """

    idp_name: StrictStr | None = Field(
        default=None,
        description="Identity provider name",
    )
    idp_slug: StrictStr | None = Field(
        default=None,
        description="Identity provider slug",
    )
    idp_icon: StrictStr | None = Field(
        default=None,
        description="Identity provider icon",
    )
    idp_icon_uploaded: StrictBool = Field(
        default=False,
        description="Whether an uploaded icon is shown instead of the icon",
    )
    idp_provider_type: StrictStr | None = Field(
        default=None,
        description="Provider type",
    )


#: One page of a user's identity-provider links.
IdentityProviderLinkPage = core_pagination.Page[IdentityProviderLinkRead]
