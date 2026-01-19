from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from core.database import Base


class IdentityProvider(Base):
    """
    Represents an external Identity Provider (IdP) configuration for authentication.

    Attributes:
        id (int): Primary key.
        name (str): Display name of the IdP.
        slug (str): URL-safe unique identifier for the IdP.
        provider_type (str): Type of provider (e.g., 'oidc', 'oauth2', 'saml').
        enabled (bool): Whether this provider is enabled for authentication.
        client_id (str, optional): OAuth2/OIDC client ID (encrypted).
        client_secret (str, optional): OAuth2/OIDC client secret (encrypted).
        issuer_url (str, optional): OIDC issuer/discovery URL.
        authorization_endpoint (str, optional): OAuth2/OIDC authorization endpoint.
        token_endpoint (str, optional): OAuth2/OIDC token endpoint.
        userinfo_endpoint (str, optional): OIDC userinfo endpoint.
        jwks_uri (str, optional): OIDC JWKS URI for token verification.
        scopes (str, optional): OAuth2/OIDC scopes to request (default: "openid profile email").
        icon (str, optional): Icon name (FontAwesome) or custom URL for the provider.
        auto_create_users (bool): Automatically create users on first login.
        sync_user_info (bool): Sync user info on each login.
        user_mapping (dict, optional): JSON mapping of IdP claims to user fields.
        created_at (datetime): Timestamp when the provider was created.
        updated_at (datetime): Timestamp when the provider was last updated.
        user_identity_providers (list[UsersIdentityProvider]): Relationship to user identity providers (many-to-many).
        oauth_states (list[OAuthState]): Relationship to OAuth states.
    """

    __tablename__ = "identity_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(length=100), nullable=False, comment="Display name of the IdP")
    slug = Column(
        String(length=50),
        nullable=False,
        unique=True,
        index=True,
        comment="URL-safe identifier",
    )
    provider_type = Column(
        String(length=50),
        nullable=False,
        default="oidc",
        comment="Type: oidc, oauth2, saml",
    )
    enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Whether this provider is enabled",
    )
    client_id = Column(
        String(length=512), nullable=True, comment="OAuth2/OIDC client ID (encrypted)"
    )
    client_secret = Column(
        String(length=512),
        nullable=True,
        comment="OAuth2/OIDC client secret (encrypted)",
    )
    issuer_url = Column(
        String(length=500), nullable=True, comment="OIDC issuer/discovery URL"
    )
    authorization_endpoint = Column(
        String(length=500), nullable=True, comment="OAuth2/OIDC authorization endpoint"
    )
    token_endpoint = Column(
        String(length=500), nullable=True, comment="OAuth2/OIDC token endpoint"
    )
    userinfo_endpoint = Column(
        String(length=500), nullable=True, comment="OIDC userinfo endpoint"
    )
    jwks_uri = Column(
        String(length=500),
        nullable=True,
        comment="OIDC JWKS URI for token verification",
    )
    scopes = Column(
        String(length=500),
        nullable=True,
        default="openid profile email",
        comment="OAuth2/OIDC scopes to request",
    )
    icon = Column(
        String(length=100),
        nullable=True,
        comment="Icon name (FontAwesome) or custom URL",
    )
    auto_create_users = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Automatically create users on first login",
    )
    sync_user_info = Column(
        Boolean, nullable=False, default=True, comment="Sync user info on each login"
    )
    user_mapping = Column(
        JSON, nullable=True, comment="JSON mapping of IdP claims to user fields"
    )
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="When this provider was created",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When this provider was last updated",
    )

    # Relationship to user identity providers (many-to-many through junction table)
    user_identity_providers = relationship(
        "UsersIdentityProvider",
        back_populates="identity_providers",
        cascade="all, delete-orphan",
    )

    # Relationship to OAuth states
    oauth_states = relationship(
        "OAuthState", back_populates="identity_provider", cascade="all, delete-orphan"
    )
