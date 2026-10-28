"""Internal identity-provider link data contracts."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class IdentityProviderDetails(Protocol):
    """Display data required to enrich a linked identity provider."""

    id: int
    name: str
    slug: str
    icon: str | None
    provider_type: str


class IdentityLinkRead(BaseModel):
    """Persisted identity-link data, including secrets for internal use."""

    id: int
    user_id: int
    idp_id: int
    idp_subject: str
    linked_at: datetime
    last_login: datetime | None
    idp_refresh_token: str | None
    idp_access_token_expires_at: datetime | None
    idp_refresh_token_updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
