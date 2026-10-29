"""Internal contracts for identity-provider persistence and OIDC flows."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class IdentityProviderState(BaseModel):
    """Stored provider configuration, including encrypted credentials."""

    id: int
    name: str
    slug: str
    provider_type: str
    enabled: bool
    client_id: str | None
    client_secret: str | None
    issuer_url: str | None
    authorization_endpoint: str | None
    token_endpoint: str | None
    userinfo_endpoint: str | None
    jwks_uri: str | None
    scopes: str | None
    icon: str | None
    auto_create_users: bool
    sync_user_info: bool
    user_mapping: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True, frozen=True)


class BrowserLinkStart(BaseModel):
    """Where to send the browser that starts a link, and the secret that binds the link to it.

    Attributes:
        authorization_url: The provider's authorization URL.
        browser_binding: The secret the starting browser keeps in a cookie; the callback requires it.
    """

    authorization_url: str
    browser_binding: str

    model_config = ConfigDict(frozen=True)
