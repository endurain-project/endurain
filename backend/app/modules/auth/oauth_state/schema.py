"""Pydantic schemas for OAuth state create/read operations."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)


class OAuthStateCreate(BaseModel):
    """
    Request to create OAuth state.

    Used internally when initiating OAuth flow. Contains all
    data needed to create a new OAuth state in database.
    """

    id: StrictStr = Field(
        ...,
        min_length=32,
        max_length=64,
        description="State parameter (secrets.token_urlsafe(32))",
    )
    idp_id: StrictInt | None = Field(None, description="Identity provider ID (may be null if mobile logic)")
    code_challenge: StrictStr | None = Field(
        None,
        min_length=43,
        max_length=128,
        description="PKCE challenge (required for mobile)",
    )
    code_challenge_method: StrictStr | None = Field(
        None, pattern="^S256$", description="PKCE method (only S256 supported)"
    )
    nonce: StrictStr = Field(..., min_length=32, max_length=64, description="OIDC nonce")
    redirect_path: StrictStr | None = Field(None, max_length=500, description="Frontend path after login")
    client_type: StrictStr = Field(..., pattern="^(web|mobile)$", description="Client type: web or mobile")
    ip_address: StrictStr | None = Field(None, max_length=45, description="Client IP address")
    expires_at: datetime = Field(..., description="Expiry timestamp")
    user_id: StrictInt | None = Field(None, description="User ID (for link mode)")


class OAuthStateRead(BaseModel):
    """
    Response with OAuth state details.

    Returned when querying OAuth state from database.
    """

    model_config = ConfigDict(from_attributes=True)

    id: StrictStr = Field(..., description="State ID")
    idp_id: StrictInt | None = Field(None, description="Identity provider ID (may be null if mobile logic)")
    code_challenge: StrictStr | None = Field(None, description="PKCE challenge")
    code_challenge_method: StrictStr | None = Field(None, description="PKCE method")
    nonce: StrictStr = Field(..., description="OIDC nonce")
    redirect_path: StrictStr | None = Field(None, description="Frontend redirect path")
    client_type: StrictStr = Field(..., description="Client type")
    ip_address: StrictStr | None = Field(None, description="Client IP")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime = Field(..., description="Expiry timestamp")
    used: StrictBool = Field(..., description="Whether state has been used")
    user_id: StrictInt | None = Field(None, description="User ID if link mode")
