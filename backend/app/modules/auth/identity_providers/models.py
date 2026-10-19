"""SQLAlchemy ORM models for the identity providers module."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from modules.auth.identity_providers.links.models import IdentityLink
    from modules.auth.oauth_state.models import OAuthState


class IdentityProvider(Base):
    """
    Represents an external Identity Provider (IdP) configuration for authentication.

    Attributes:
        id (int): Primary key.
        name (str): Display name of the IdP.
        slug (str): URL-safe unique identifier for the IdP.
        provider_type (str): Type of provider (e.g., 'oidc', 'oauth2', 'saml').
        enabled (bool): Whether this provider is enabled for authentication.
        client_id (str | None): OAuth2/OIDC client ID (encrypted).
        client_secret (str | None): OAuth2/OIDC client secret (encrypted).
        issuer_url (str | None): OIDC issuer/discovery URL.
        authorization_endpoint (str | None): OAuth2/OIDC authorization endpoint.
        token_endpoint (str | None): OAuth2/OIDC token endpoint.
        userinfo_endpoint (str | None): OIDC userinfo endpoint.
        jwks_uri (str | None): OIDC JWKS URI for token verification.
        scopes (str | None): OAuth2/OIDC scopes to request
            (default: "openid profile email").
        icon (str | None): Icon name (FontAwesome) or custom URL for the provider.
        auto_create_users (bool): Automatically create users on first login.
        sync_user_info (bool): Sync user info on each login.
        user_mapping (dict[str, Any] | None): JSON mapping of IdP claims to user
            fields.
        created_at (datetime): Timestamp when the provider was created.
        updated_at (datetime): Timestamp when the provider was last updated.
        user_identity_providers (list[IdentityLink]): Relationship to
            user identity providers (many-to-many through junction table).
        oauth_states (list[OAuthState]): Relationship to OAuth states.
    """

    __tablename__ = "identity_providers"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Display name of the IdP",
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe identifier",
    )
    provider_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="oidc",
        comment="Type: oidc, oauth2, saml",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether this provider is enabled",
    )
    client_id: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="OAuth2/OIDC client ID (encrypted)",
    )
    client_secret: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="OAuth2/OIDC client secret (encrypted)",
    )
    issuer_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="OIDC issuer/discovery URL",
    )
    authorization_endpoint: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="OAuth2/OIDC authorization endpoint",
    )
    token_endpoint: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="OAuth2/OIDC token endpoint",
    )
    userinfo_endpoint: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="OIDC userinfo endpoint",
    )
    jwks_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="OIDC JWKS URI for token verification",
    )
    scopes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        default="openid profile email",
        comment="OAuth2/OIDC scopes to request",
    )
    icon: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Icon name (FontAwesome) or custom URL",
    )
    auto_create_users: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Automatically create users on first login",
    )
    sync_user_info: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Sync user info on each login",
    )
    user_mapping: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="JSON mapping of IdP claims to user fields",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When this provider was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When this provider was last updated",
    )

    # Relationship to user identity providers (many-to-many through junction table)
    user_identity_providers: Mapped[list["IdentityLink"]] = relationship(
        back_populates="identity_providers",
        cascade="all, delete-orphan",
    )

    # Relationship to OAuth states
    oauth_states: Mapped[list["OAuthState"]] = relationship(
        back_populates="identity_provider",
        cascade="all, delete-orphan",
    )
