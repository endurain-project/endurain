"""User Identity Provider schemas"""
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class UserIdentityProviderBase(BaseModel):
    """
    Base schema for a user's identity provider association.

    This is an internal junction table schema, not exposed via API endpoints.
    Links are managed by the identity provider service during SSO authentication.
    
    Attributes:
        user_id (int): User ID.
        idp_id (int): Identity Provider ID.
        idp_subject (str): Subject/ID from the identity provider (max length: 500).
    """
    user_id: int = Field(..., description="User ID")
    idp_id: int = Field(..., description="Identity Provider ID")
    idp_subject: str = Field(
        ...,
        max_length=500,
        description="Subject/ID from the identity provider"
    )


class UserIdentityProviderResponse(UserIdentityProviderBase):
    """
    Response schema for user identity provider link.
    
    Includes all base fields plus auto-generated metadata.
    """
    id: int = Field(..., description="Link ID")
    linked_at: datetime = Field(..., description="When this IdP was linked")
    last_login: datetime | None = Field(
        None,
        description="Last time user logged in with this IdP"
    )

    model_config = ConfigDict(from_attributes=True)
