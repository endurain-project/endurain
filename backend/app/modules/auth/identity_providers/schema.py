"""Pydantic schemas for the identity providers module."""

import re
from datetime import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_serializer,
    field_validator,
)

import core.cryptography as core_cryptography
import modules.auth.identity_providers.constants as idp_constants


class IdentityProviderBase(BaseModel):
    """Base schema for an Identity Provider (IdP) configuration.

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
        icon (str | None): Built-in icon key; any other logo is uploaded instead.
        auto_create_users (bool): Whether to auto-create users on first login. Defaults to True.
        sync_user_info (bool): Whether to sync user info on each login. Defaults to True.
        user_mapping (Dict[str, Any] | None): Claims mapping configuration.
        client_id (str | None): The client ID for the provider (1-512 characters).

    Validators:
        - slug: Ensures the slug contains only lowercase letters, numbers, and hyphens.
        - provider_type: Ensures the provider type is one of the allowed values.
        - icon: Ensures the icon is a built-in icon key.
    """

    name: StrictStr = Field(..., max_length=100, min_length=1, description="Display name of the IdP")
    slug: StrictStr = Field(..., max_length=50, min_length=1, description="URL-safe identifier")
    provider_type: StrictStr = Field(default="oidc", description="Provider type: oidc, oauth2, or saml")
    enabled: StrictBool = Field(default=False, description="Whether this provider is enabled")
    issuer_url: StrictStr | None = Field(default=None, max_length=500, description="OIDC issuer/discovery URL")
    authorization_endpoint: StrictStr | None = Field(
        default=None, max_length=500, description="OAuth2/OIDC authorization endpoint"
    )
    token_endpoint: StrictStr | None = Field(default=None, max_length=500, description="OAuth2/OIDC token endpoint")
    userinfo_endpoint: StrictStr | None = Field(default=None, max_length=500, description="OIDC userinfo endpoint")
    jwks_uri: StrictStr | None = Field(default=None, max_length=500, description="OIDC JWKS URI")
    scopes: StrictStr = Field(
        default="openid profile email",
        max_length=500,
        description="OAuth2/OIDC scopes",
    )
    icon: StrictStr | None = Field(default=None, description="Built-in icon key")
    auto_create_users: StrictBool = Field(default=True, description="Auto-create users on first login")
    sync_user_info: StrictBool = Field(default=True, description="Sync user info on each login")
    user_mapping: dict[str, Any] | None = Field(default=None, description="Claims mapping configuration")
    client_id: StrictStr | None = Field(default=None, min_length=1, max_length=512)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validates that the provided slug contains only lowercase letters, numbers, and hyphens.

        Args:
            v (str): The slug string to validate.

        Returns:
            str: The validated slug string.

        Raises:
            ValueError: If the slug contains characters other than lowercase letters, numbers, or hyphens.
        """
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        return v

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v: str | None) -> str | None:
        """Validates that the icon is one of the built-in icon keys.

        Args:
            v (str | None): The icon key to validate.

        Returns:
            str | None: The validated icon key.

        Raises:
            ValueError: If the icon is not a built-in icon key.
        """
        if v is not None and v not in idp_constants.BUILTIN_ICONS:
            raise ValueError(f"Icon must be one of: {', '.join(sorted(idp_constants.BUILTIN_ICONS))}")
        return v

    @field_validator("provider_type")
    @classmethod
    def validate_provider_type(cls, v: str) -> str:
        """Validates that the given provider type is one of the allowed values.

        Args:
            v (str): The provider type to validate.

        Returns:
            str: The validated provider type.

        Raises:
            ValueError: If the provider type is not one of 'oidc', 'oauth2', or 'saml'.
        """
        allowed = ["oidc", "oauth2", "saml"]
        if v not in allowed:
            raise ValueError(f"Provider type must be one of: {', '.join(allowed)}")
        return v


class IdentityProviderCreate(IdentityProviderBase):
    """Schema for creating a new Identity Provider.

    Inherits from:
        IdentityProviderBase

    Attributes:
        client_secret (str): OAuth2/OIDC client secret. Must be between 1 and 512 characters.
    """

    client_secret: StrictStr = Field(..., min_length=1, max_length=512, description="OAuth2/OIDC client secret")

    model_config = ConfigDict(extra="forbid")


class IdentityProviderUpdate(IdentityProviderBase):
    """Schema for updating an existing Identity Provider.

    Inherits from:
        IdentityProviderBase

    Attributes:
        client_secret (str | None): The client secret for the provider (1-512 characters).
    """

    client_secret: StrictStr | None = Field(default=None, min_length=1, max_length=512)

    model_config = ConfigDict(extra="forbid")


class IdentityProviderRead(IdentityProviderBase):
    """Represents an identity provider with decrypted client credentials.

    Inherits from:
        IdentityProviderBase

    Attributes:
        id (int): Unique identifier of the identity provider.
        icon_uploaded (bool): Whether an uploaded icon is shown instead of ``icon``.
        created_at (datetime): Timestamp when the identity provider was created.
        updated_at (datetime): Timestamp when the identity provider was last updated.
        version (int): Optimistic-concurrency counter, also sent as the ETag.

    Config:
        model_config (ConfigDict): Pydantic model configuration to enable attribute-based initialization,
            forbid extra fields, and validate assignment.

    Methods:
        decrypt_client_id():
            Decrypts the `client_id` attribute after loading from the database.

                IdentityProviderRead: The instance with the decrypted `client_id`.
    """

    id: StrictInt
    icon_uploaded: StrictBool = Field(default=False, description="Whether an uploaded icon is shown instead of icon")
    created_at: datetime
    updated_at: datetime
    version: StrictInt = Field(
        default=1,
        ge=1,
        description="Optimistic-concurrency counter, also sent as the ETag",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)

    @field_serializer("client_id")
    def serialize_client_id(self, value: str | None) -> str | None:
        """Decrypt client_id for serialization."""
        if value and value.startswith("gAAAAAB"):
            return core_cryptography.decrypt_token_fernet(value)
        return value


class IdentityProviderIconRead(BaseModel):
    """The state of a provider's uploaded icon after an upload.

    Attributes:
        version (int): The provider version that identifies the stored icon.
    """

    version: StrictInt

    model_config = ConfigDict(extra="forbid")


class IdentityProviderPublicRead(BaseModel):
    """Represents the public-facing information of an identity provider.

    Attributes:
        id (int): Unique identifier of the identity provider.
        name (str): Display name of the identity provider.
        slug (str): URL-friendly unique identifier for the provider.
        icon (str | None): URL or path to the provider's icon image.
        icon_uploaded (bool): Whether an uploaded icon is shown instead of ``icon``.

    Config:
        model_config (dict): Pydantic model configuration to allow population from ORM attributes.
    """

    id: StrictInt
    name: StrictStr
    slug: StrictStr
    icon: StrictStr | None = None
    icon_uploaded: StrictBool = False

    model_config = ConfigDict(from_attributes=True, extra="forbid", validate_assignment=True)


class IdentityProviderTemplateRead(BaseModel):
    """Represents a template for an identity provider configuration.

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

    template_id: StrictStr = Field(..., description="Template identifier (e.g., 'keycloak', 'authentik')")
    name: StrictStr
    provider_type: StrictStr
    issuer_url: StrictStr | None = None
    scopes: StrictStr
    icon: StrictStr | None = None
    user_mapping: dict[str, Any] | None = None
    description: StrictStr = Field(..., description="Description of this template")
    configuration_notes: StrictStr | None = Field(default=None, description="Setup instructions for this IdP")


class IdpReauthProof(BaseModel):
    """Proof that a password-less account signed in again with its identity provider.

    The provider's callback hands the ticket to the browser that started the step-up; that browser also holds
    the PKCE verifier whose challenge the ticket records, so a ticket alone cannot be redeemed.

    Attributes:
        ticket: The single-use step-up ticket.
        code_verifier: The PKCE verifier the step-up was started with.
    """

    ticket: StrictStr = Field(..., min_length=43, max_length=64, description="Single-use step-up ticket")
    code_verifier: StrictStr = Field(
        ..., min_length=43, max_length=128, description="PKCE verifier the step-up was started with"
    )

    model_config = ConfigDict(extra="forbid")


class StepUpStartRequest(BaseModel):
    """Start a step-up re-authentication with a linked identity provider.

    Attributes:
        code_challenge: S256 challenge of a PKCE verifier the browser keeps until it sends the sensitive request.
        action: The sensitive operation the step-up authorises.
        redirect: Relative frontend path the provider's callback returns to.
    """

    code_challenge: StrictStr = Field(..., min_length=43, max_length=128, description="PKCE S256 challenge")
    action: idp_constants.StepUpAction = Field(..., description="Sensitive operation the step-up authorises")
    redirect: StrictStr = Field(..., min_length=1, max_length=500, description="Relative path to return to")

    model_config = ConfigDict(extra="forbid")


class StepUpStartRead(BaseModel):
    """Where to send the browser for a step-up re-authentication.

    Attributes:
        authorization_url: The identity provider's authorization URL.
    """

    authorization_url: StrictStr = Field(..., description="Identity provider authorization URL")
