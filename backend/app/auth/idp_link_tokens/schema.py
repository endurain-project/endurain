from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class IdpLinkTokenCreate(BaseModel):
    """Schema for creating an IdP link token."""

    id: str = Field(..., description="Random token ID")
    user_id: int = Field(..., description="User ID linking the IdP")
    idp_id: int = Field(..., description="Identity provider ID being linked")
    created_at: datetime = Field(..., description="Token creation timestamp")
    expires_at: datetime = Field(..., description="Token expiration timestamp")
    used: bool = Field(default=False, description="Token usage flag")
    ip_address: str | None = Field(None, description="Client IP address")


class IdpLinkTokenResponse(BaseModel):
    """Schema for IdP link token response."""

    token: str = Field(..., description="One-time link token")
    expires_at: datetime = Field(..., description="Token expiration timestamp")

    model_config = ConfigDict(from_attributes=True)
