from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class OAuthStateCreate(BaseModel):
    """
    Request to create OAuth state.

    Used internally when initiating OAuth flow. Contains all
    data needed to create a new OAuth state in database.
    """

    id: str = Field(
        ...,
        min_length=32,
        max_length=64,
        description="State parameter (secrets.token_urlsafe(32))",
    )
    idp_id: int | None = Field(
        None, description="Identity provider ID (may be null if mobile logic)"
    )
    code_challenge: Optional[str] = Field(
        None,
        min_length=43,
        max_length=128,
        description="PKCE challenge (required for mobile)",
    )
    code_challenge_method: Optional[str] = Field(
        None, pattern="^S256$", description="PKCE method (only S256 supported)"
    )
    nonce: str = Field(..., min_length=32, max_length=64, description="OIDC nonce")
    redirect_path: Optional[str] = Field(
        None, max_length=500, description="Frontend path after login"
    )
    client_type: str = Field(
        ..., pattern="^(web|mobile)$", description="Client type: web or mobile"
    )
    ip_address: Optional[str] = Field(
        None, max_length=45, description="Client IP address"
    )
    expires_at: datetime = Field(..., description="Expiry timestamp")
    user_id: Optional[int] = Field(None, description="User ID (for link mode)")


class OAuthStateRead(BaseModel):
    """
    Response with OAuth state details.

    Returned when querying OAuth state from database.
    """

    id: str = Field(..., description="State ID")
    idp_id: int | None = Field(
        None, description="Identity provider ID (may be null if mobile logic)"
    )
    code_challenge: Optional[str] = Field(None, description="PKCE challenge")
    code_challenge_method: Optional[str] = Field(None, description="PKCE method")
    nonce: str = Field(..., description="OIDC nonce")
    redirect_path: Optional[str] = Field(None, description="Frontend redirect path")
    client_type: str = Field(..., description="Client type")
    ip_address: Optional[str] = Field(None, description="Client IP")
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: datetime = Field(..., description="Expiry timestamp")
    used: bool = Field(..., description="Whether state has been used")
    user_id: Optional[int] = Field(None, description="User ID if link mode")

    class Config:
        from_attributes = True
