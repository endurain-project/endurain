from pydantic import BaseModel, Field, field_validator, field_serializer, ConfigDict
from typing import Dict, Any
from datetime import datetime
import re

import core.cryptography as core_cryptography


class IdentityProviderBase(BaseModel):
    """
    Base schema for an Identity Provider (IdP) configuration.

    Attributes:
        name (str): Display name of the IdP (1-100 characters).
        slug (str): URL-safe identifier (1-50 characters, lowercase alphanumeric and hyphens only).
        provider_type (str): Type of provider; must be one of 'oidc', 'oauth2', or 'saml'. Defaults to 'oidc'.
        enabled (bool): Whether this provider is enabled. Defaults to False.
        issuer_url (str | None): OIDC issuer/discovery URL (max 500 characters).
        authorization_endpoint (str | None): OAuth2/OIDC authorization endpoint (max 500 characters).
        token_endpoint (str | None): OAuth2/OIDC token endpoint (max 500 characters).
        userinfo_endpoint (str | None): OIDC userinfo endpoint (max 500 characters).
        jwks_uri (str | None): OIDC JWKS URI (max 500 characters).
        scopes (str): OAuth2/OIDC scopes (max 500 characters). Defaults to "openid profile email".
        icon (str | None): Icon name or URL (max 100 characters).
        auto_create_users (bool): Whether to auto-create users on first login. Defaults to True.
        sync_user_info (bool): Whether to sync user info on each login. Defaults to True.
        user_mapping (Dict[str, Any] | None): Claims mapping configuration.
        client_id (str | None): The client ID for the provider (1-512 characters).

    Validators:
        - slug: Ensures the slug contains only lowercase letters, numbers, and hyphens.
        - provider_type: Ensures the provider type is one of the allowed values.
    """

    name: str = Field(
        ..., max_length=100, min_length=1, description="Display name of the IdP"
    )
    slug: str = Field(
        ..., max_length=50, min_length=1, description="URL-safe identifier"
    )
    provider_type: str = Field(
        default="oidc", description="Provider type: oidc, oauth2, or saml"
    )
    enabled: bool = Field(default=False, description="Whether this provider is enabled")
    issuer_url: str | None = Field(
        None, max_length=500, description="OIDC issuer/discovery URL"
    )
    authorization_endpoint: str | None = Field(
        None, max_length=500, description="OAuth2/OIDC authorization endpoint"
    )
    token_endpoint: str | None = Field(
        None, max_length=500, description="OAuth2/OIDC token endpoint"
    )
    userinfo_endpoint: str | None = Field(
        None, max_length=500, description="OIDC userinfo endpoint"
    )
    jwks_uri: str | None = Field(None, max_length=500, description="OIDC JWKS URI")
    scopes: str = Field(
        default="openid profile email", max_length=500, description="OAuth2/OIDC scopes"
    )
    icon: str | None = Field(None, max_length=100, description="Icon name or URL")
    auto_create_users: bool = Field(
        default=True, description="Auto-create users on first login"
    )
    sync_user_info: bool = Field(
        default=True, description="Sync user info on each login"
    )
    user_mapping: Dict[str, Any] | None = Field(
        None, description="Claims mapping configuration"
    )
    client_id: str | None = Field(None, min_length=1, max_length=512)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """
        Validates that the provided slug contains only lowercase letters, numbers, and hyphens.

        Args:
            v (str): The slug string to validate.

        Returns:
            str: The validated slug string.

        Raises:
            ValueError: If the slug contains characters other than lowercase letters, numbers, or hyphens.
        """
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "Slug must contain only lowercase letters, numbers, and hyphens"
            )
        return v

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        """
        Validates that the given provider type is one of the allowed values.

        Args:
            v (str): The provider type to validate.

        Returns:
            str: The validated provider type.

        Raises:
            ValueError: If the provider type is not one of 'oidc', 'oauth2', or 'saml'.
        """
        allowed = ["oidc", "oauth2", "saml"]
        if v not in allowed:
            raise ValueError(f'Provider type must be one of: {", ".join(allowed)}')
        return v


class IdentityProviderCreate(IdentityProviderBase):
    """
    Schema for creating a new Identity Provider.

    Inherits from:
        IdentityProviderBase

    Attributes:
        client_secret (str): OAuth2/OIDC client secret. Must be between 1 and 512 characters.
    """

    client_secret: str = Field(
        ..., min_length=1, max_length=512, description="OAuth2/OIDC client secret"
    )


class IdentityProviderUpdate(IdentityProviderBase):
    """
    Schema for updating an existing Identity Provider.

    Inherits from:
        IdentityProviderBase

    Attributes:
        client_secret (str | None): The client secret for the provider (1-512 characters).
    """

    client_secret: str | None = Field(None, min_length=1, max_length=512)


class IdentityProvider(IdentityProviderBase):
    """
    Represents an identity provider with decrypted client credentials.

    Inherits from:
        IdentityProviderBase

    Attributes:
        id (int): Unique identifier of the identity provider.
        created_at (datetime): Timestamp when the identity provider was created.
        updated_at (datetime): Timestamp when the identity provider was last updated.

    Config:
        model_config (ConfigDict): Pydantic model configuration to enable attribute-based initialization,
            forbid extra fields, and validate assignment.

    Methods:
        decrypt_client_id():
            Decrypts the `client_id` attribute after loading from the database.

                IdentityProvider: The instance with the decrypted `client_id`.
    """

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )

    @field_serializer("client_id")
    def serialize_client_id(self, value: str | None) -> str | None:
        """Decrypt client_id for serialization."""
        if value and value.startswith("gAAAAAB"):
            return core_cryptography.decrypt_token_fernet(value)
        return value


class IdentityProviderPublic(BaseModel):
    """
    Represents the public-facing information of an identity provider.

    Attributes:
        id (int): Unique identifier of the identity provider.
        name (str): Display name of the identity provider.
        slug (str): URL-friendly unique identifier for the provider.
        icon (str | None): URL or path to the provider's icon image.

    Config:
        model_config (dict): Pydantic model configuration to allow population from ORM attributes.
    """

    id: int
    name: str
    slug: str
    icon: str | None = None

    model_config = ConfigDict(
        from_attributes=True, extra="forbid", validate_assignment=True
    )


class IdentityProviderTemplate(BaseModel):
    """
    Represents a template for an identity provider configuration.

    Attributes:
        template_id (str): Template identifier (e.g., 'keycloak', 'authentik').
        name (str): Human-readable name of the identity provider template.
        provider_type (str): Type of the identity provider (e.g., 'oidc', 'saml').
        issuer_url (str | None): URL of the identity provider's issuer, if applicable.
        scopes (str): Scopes required for authentication.
        icon (str | None): URL or path to the icon representing the identity provider.
        user_mapping (Dict[str, Any] | None): Mapping configuration for user attributes.
        description (str): Description of this template.
        configuration_notes (str | None): Setup instructions for this identity provider.
    """

    template_id: str = Field(
        ..., description="Template identifier (e.g., 'keycloak', 'authentik')"
    )
    name: str
    provider_type: str
    issuer_url: str | None = None
    scopes: str
    icon: str | None = None
    user_mapping: Dict[str, Any] | None = None
    description: str = Field(..., description="Description of this template")
    configuration_notes: str | None = Field(
        None, description="Setup instructions for this IdP"
    )


class TokenExchangeRequest(BaseModel):
    """
    Request schema for mobile PKCE token exchange.

    After OAuth callback completes, mobile clients exchange the session_id
    for actual JWT tokens by proving they possess the code_verifier that
    matches the code_challenge sent during login initiation.

    Attributes:
        code_verifier (str): PKCE code verifier (43-128 chars, base64url).
            Must hash to the code_challenge stored in OAuth state.
    """

    code_verifier: str = Field(
        ...,
        min_length=43,
        max_length=128,
        description="PKCE code verifier (base64url, 43-128 chars)",
    )

    @field_validator("code_verifier")
    @classmethod
    def validate_code_verifier(cls, v: str) -> str:
        """
        Validate PKCE code_verifier format according to RFC 7636.

        Args:
            v (str): The code verifier string.

        Returns:
            str: The validated code verifier.

        Raises:
            ValueError: If format is invalid (wrong length or characters).
        """
        if not re.match(r"^[A-Za-z0-9_-]+$", v):
            raise ValueError("code_verifier must be valid base64url")
        return v


class TokenExchangeResponse(BaseModel):
    """
    Response schema for successful PKCE token exchange.

    Returns the actual JWT tokens that clients need for API access.
    Response format varies by client type:
    - Web clients: access_token, csrf_token (refresh_token in httpOnly cookie)
    - Mobile clients: access_token, refresh_token (no CSRF token)

    Attributes:
        session_id (str): Session identifier.
        access_token (str): JWT access token (15-minute expiry).
        refresh_token (str | None): JWT refresh token (7-day expiry). Only for mobile clients.
        csrf_token (str | None): CSRF protection token. Only for web clients.
        expires_in (int): Access token lifetime in seconds (900 = 15 minutes).
        token_type (str): Token type, always "Bearer".
    """

    session_id: str = Field(..., description="Session identifier")
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str | None = Field(
        default=None, description="JWT refresh token (mobile only)"
    )
    csrf_token: str | None = Field(
        default=None, description="CSRF protection token (web only)"
    )
    expires_in: int = Field(default=900, description="Access token lifetime in seconds")
    token_type: str = Field(default="Bearer", description="Token type")
