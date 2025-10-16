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
    
    Includes all base fields plus auto-generated metadata and enriched IDP details.
    
    Security Note:
        The actual `idp_refresh_token` is intentionally NOT included in this schema.
        Only metadata about the token (expiry times) is exposed for security reasons.
    
    Enriched Fields:
        idp_name, idp_slug, idp_icon, idp_provider_type are added by the API layer
        for frontend display convenience (not stored in this table).
    """
    id: int = Field(..., description="Link ID")
    linked_at: datetime = Field(..., description="When this IdP was linked")
    last_login: datetime | None = Field(
        None,
        description="Last time user logged in with this IdP"
    )
    idp_access_token_expires_at: datetime | None = Field(
        None,
        description="When the IdP access token expires (for reference)"
    )
    idp_refresh_token_updated_at: datetime | None = Field(
        None,
        description="When the refresh token was last obtained or refreshed"
    )
    # Enriched fields (added by API layer, not in database)
    idp_name: str | None = Field(None, description="Identity provider name")
    idp_slug: str | None = Field(None, description="Identity provider slug")
    idp_icon: str | None = Field(None, description="Identity provider icon")
    idp_provider_type: str | None = Field(None, description="Provider type (oidc, oauth2, etc.)")

    model_config = ConfigDict(from_attributes=True)


class UserIdentityProviderTokenUpdate(BaseModel):
    """
    Internal schema for updating IdP token data.
    
    This schema is used only by the service layer and NEVER exposed via API endpoints.
    The refresh token should always be encrypted before being stored.
    
    Security Note:
        - This schema contains the encrypted refresh token
        - Never use this schema in API responses
        - Only used for internal CRUD operations
    
    Attributes:
        idp_refresh_token (str | None): Encrypted refresh token from IdP (Fernet encrypted).
        idp_access_token_expires_at (datetime | None): When the access token expires.
        idp_refresh_token_updated_at (datetime | None): When the refresh token was last updated.
    """
    idp_refresh_token: str | None = Field(
        None,
        description="Encrypted refresh token from IdP (already Fernet encrypted)"
    )
    idp_access_token_expires_at: datetime | None = Field(
        None,
        description="When the IdP access token expires"
    )
    idp_refresh_token_updated_at: datetime | None = Field(
        None,
        description="When the refresh token was last obtained/refreshed"
    )

    model_config = ConfigDict(from_attributes=True)
