"""Internal identity-provider link data contracts."""

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class IdentityProviderDetails(Protocol):
    """Display data required to enrich a linked identity provider."""

    @property
    def id(self) -> int:
        """The provider's id."""
        ...

    @property
    def name(self) -> str:
        """The provider's display name."""
        ...

    @property
    def slug(self) -> str:
        """The provider's URL slug."""
        ...

    @property
    def icon(self) -> str | None:
        """The provider's icon, or ``None``."""
        ...

    @property
    def icon_uploaded(self) -> bool:
        """Whether the icon is an uploaded file."""
        ...

    @property
    def provider_type(self) -> str:
        """The protocol the provider speaks."""
        ...


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
