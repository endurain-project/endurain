"""Pydantic schemas for the identity providers module."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_serializer,
    model_validator,
)

import core.cryptography as core_cryptography
import core.pagination as core_pagination
import core.partial_update as core_partial_update
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.utils as idp_utils
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.schema as auth_schema


def _validate_slug(v: str) -> str:
    """Validate that a slug contains only lowercase letters, numbers, and hyphens and is not reserved.

    Args:
        v: The slug string to validate.

    Returns:
        The validated slug string.

    Raises:
        ValueError: If the slug contains characters other than lowercase letters, numbers, or hyphens, or is a
            word the public identity-provider routes use.
    """
    if not re.match(r"^[a-z0-9-]+$", v):
        raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
    if v in idp_constants.RESERVED_SLUGS:
        raise ValueError(f"Slug '{v}' is reserved; choose another")
    return v


def _validate_icon(v: str | None) -> str | None:
    """Validate that the icon is one of the built-in icon keys.

    Args:
        v: The icon key to validate.

    Returns:
        The validated icon key.

    Raises:
        ValueError: If the icon is not a built-in icon key.
    """
    if v is not None and v not in idp_constants.BUILTIN_ICONS:
        raise ValueError(f"Icon must be one of: {', '.join(sorted(idp_constants.BUILTIN_ICONS))}")
    return v


#: Display name of a provider.
ProviderName = Annotated[StrictStr, Field(max_length=100, min_length=1)]

#: URL-safe identifier of a provider.
ProviderSlug = Annotated[StrictStr, Field(max_length=50, min_length=1), AfterValidator(_validate_slug)]

#: Built-in icon key of a provider.
ProviderIcon = Annotated[StrictStr, AfterValidator(_validate_icon)]

#: A provider endpoint or issuer URL.
ProviderUrl = Annotated[StrictStr, Field(max_length=500)]

#: The scopes a provider requests.
ProviderScopes = Annotated[StrictStr, Field(max_length=500)]


class IdentityProviderBase(BaseModel):
    """Base schema for an Identity Provider (IdP) configuration.

    Attributes:
        name (str): Display name of the IdP (1-100 characters).
        slug (str): URL-safe identifier (1-50 characters, lowercase alphanumeric and hyphens only).
        provider_type (ProviderType): Protocol of the provider, 'oidc' or 'oauth2'. Defaults to 'oidc'.
        enabled (bool): Whether this provider is enabled. Defaults to False.
        issuer_url (str | None): OIDC issuer/discovery URL (max 500 characters).
        authorization_endpoint (str | None): OAuth2/OIDC authorization endpoint (max 500 characters).
        token_endpoint (str | None): OAuth2/OIDC token endpoint (max 500 characters).
        userinfo_endpoint (str | None): OIDC userinfo endpoint (max 500 characters).
        scopes (str): OAuth2/OIDC scopes (max 500 characters). Defaults to "openid profile email".
        icon (str | None): Built-in icon key; any other logo is uploaded instead.
        auto_create_users (bool): Whether to auto-create users on first login. Defaults to True.
        link_by_email (bool): Whether a sign-in with no link joins the local account that has the same verified
            email. Defaults to False.
        sync_user_info (bool): Whether to sync the mapped profile fields, except the email, on each login.
            Defaults to True.
        sync_email (bool): Whether to sync the verified email on each login. Defaults to False.
        user_mapping (Dict[str, Any] | None): Claims mapping configuration.

    """

    name: ProviderName = Field(..., description="Display name of the IdP")
    slug: ProviderSlug = Field(..., description="URL-safe identifier")
    provider_type: idp_constants.ProviderType = Field(
        default=idp_constants.ProviderType.OIDC,
        description=(
            "Protocol of the provider: oidc, or oauth2. With the openid scope an oauth2 provider's sign-in "
            "must carry a verified ID token too"
        ),
    )
    enabled: StrictBool = Field(default=False, description="Whether this provider is enabled")
    issuer_url: ProviderUrl | None = Field(default=None, description="OIDC issuer/discovery URL")
    authorization_endpoint: ProviderUrl | None = Field(default=None, description="OAuth2/OIDC authorization endpoint")
    token_endpoint: ProviderUrl | None = Field(default=None, description="OAuth2/OIDC token endpoint")
    userinfo_endpoint: ProviderUrl | None = Field(default=None, description="OIDC userinfo endpoint")
    scopes: ProviderScopes = Field(default=idp_constants.DEFAULT_SCOPES, description="OAuth2/OIDC scopes")
    icon: ProviderIcon | None = Field(default=None, description="Built-in icon key")
    auto_create_users: StrictBool = Field(default=True, description="Auto-create users on first login")
    link_by_email: StrictBool = Field(
        default=False,
        description=(
            "Link a sign-in that has no link yet to the local account with the same verified email. "
            "When off, that sign-in is refused and the user links the provider from their settings"
        ),
    )
    sync_user_info: StrictBool = Field(
        default=True, description="Sync the mapped profile fields, except the email, on each login"
    )
    sync_email: StrictBool = Field(
        default=False, description="Sync the email the provider verified onto the local account on each login"
    )
    user_mapping: dict[str, Any] | None = Field(default=None, description="Claims mapping configuration")


class IdentityProviderCreate(IdentityProviderBase):
    """Schema for creating a new Identity Provider.

    Inherits from:
        IdentityProviderBase

    Attributes:
        client_id (str): OAuth2/OIDC client ID. Must be between 1 and 512 characters.
        client_secret (str): OAuth2/OIDC client secret. Must be between 1 and 512 characters.

    Validators:
        - OIDC requirements: an ``oidc`` provider needs an issuer URL and the ``openid`` scope.
    """

    client_id: StrictStr = Field(..., min_length=1, max_length=512)
    client_secret: StrictStr = Field(..., min_length=1, max_length=512, description="OAuth2/OIDC client secret")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_oidc_requirements(self) -> IdentityProviderCreate:
        """Refuse an ``oidc`` provider that has no issuer URL or no ``openid`` scope.

        Returns:
            The validated provider.

        Raises:
            ValueError: If the provider is ``oidc`` and the issuer URL or the ``openid`` scope is missing.
        """
        problem = idp_utils.oidc_requirements_problem(self.provider_type, self.issuer_url, self.scopes)
        if problem is not None:
            raise ValueError(problem)
        return self


class IdentityProviderUpdate(core_partial_update.NotClearable, BaseModel):
    """Partial update of an Identity Provider: omit a field to keep it, send null to clear a nullable one.

    Every field has the type and limits of ``IdentityProviderBase``. A field the provider always has refuses
    null. The rules that span several fields, such as an ``oidc`` provider needing an issuer URL, are checked by
    the service against the stored provider with these changes applied.

    Attributes:
        name: Display name of the IdP.
        slug: URL-safe identifier.
        provider_type: Protocol of the provider, 'oidc' or 'oauth2'.
        enabled: Whether this provider is enabled.
        client_id: The client ID for the provider (1-512 characters).
        client_secret: The client secret for the provider (1-512 characters).
        issuer_url: OIDC issuer/discovery URL.
        authorization_endpoint: OAuth2/OIDC authorization endpoint.
        token_endpoint: OAuth2/OIDC token endpoint.
        userinfo_endpoint: OIDC userinfo endpoint.
        scopes: OAuth2/OIDC scopes.
        icon: Built-in icon key.
        auto_create_users: Whether to auto-create users on first login.
        link_by_email: Whether a sign-in with no link joins the local account with the same verified email.
        sync_user_info: Whether to sync the mapped profile fields, except the email, on each login.
        sync_email: Whether to sync the verified email on each login.
        user_mapping: Claims mapping configuration.
    """

    not_clearable = (
        "name",
        "slug",
        "provider_type",
        "enabled",
        "client_id",
        "client_secret",
        "scopes",
        "auto_create_users",
        "link_by_email",
        "sync_user_info",
        "sync_email",
    )

    name: ProviderName | None = Field(default=None, description="Display name of the IdP")
    slug: ProviderSlug | None = Field(default=None, description="URL-safe identifier")
    provider_type: idp_constants.ProviderType | None = Field(
        default=None, description="Protocol of the provider: oidc, or oauth2"
    )
    enabled: StrictBool | None = Field(default=None, description="Whether this provider is enabled")
    client_id: StrictStr | None = Field(default=None, min_length=1, max_length=512)
    client_secret: StrictStr | None = Field(default=None, min_length=1, max_length=512)
    issuer_url: ProviderUrl | None = Field(default=None, description="OIDC issuer/discovery URL")
    authorization_endpoint: ProviderUrl | None = Field(default=None, description="OAuth2/OIDC authorization endpoint")
    token_endpoint: ProviderUrl | None = Field(default=None, description="OAuth2/OIDC token endpoint")
    userinfo_endpoint: ProviderUrl | None = Field(default=None, description="OIDC userinfo endpoint")
    scopes: ProviderScopes | None = Field(default=None, description="OAuth2/OIDC scopes")
    icon: ProviderIcon | None = Field(default=None, description="Built-in icon key")
    auto_create_users: StrictBool | None = Field(default=None, description="Auto-create users on first login")
    link_by_email: StrictBool | None = Field(
        default=None,
        description="Link a sign-in that has no link yet to the local account with the same verified email",
    )
    sync_user_info: StrictBool | None = Field(
        default=None, description="Sync the mapped profile fields, except the email, on each login"
    )
    sync_email: StrictBool | None = Field(
        default=None, description="Sync the email the provider verified onto the local account on each login"
    )
    user_mapping: dict[str, Any] | None = Field(default=None, description="Claims mapping configuration")

    model_config = ConfigDict(extra="forbid")


class IdentityProviderCreateRequest(IdentityProviderCreate):
    """The body of ``POST /identity-providers``: a new provider and the administrator's step-up.

    Attributes:
        step_up: The administrator's own step-up verification; it is never a provider field.
    """

    step_up: auth_schema.StepUpVerification = Field(
        ..., description="The administrator's step-up verification, required to add an identity provider"
    )

    def to_create(self) -> IdentityProviderCreate:
        """Return the provider fields of the request, without the step-up.

        Returns:
            The provider as an :class:`IdentityProviderCreate`.
        """
        return IdentityProviderCreate.model_validate(self.model_dump(exclude={"step_up"}))


class IdentityProviderUpdateRequest(IdentityProviderUpdate):
    """The body of ``PATCH /identity-providers/{idp_id}``: the provider changes and the administrator's step-up.

    Attributes:
        step_up: The administrator's own step-up verification; it is never a provider field.
    """

    step_up: auth_schema.StepUpVerification = Field(
        ..., description="The administrator's step-up verification, required to edit an identity provider"
    )

    def to_update(self) -> IdentityProviderUpdate:
        """Return the provider fields the client sent, without the step-up.

        Returns:
            The changes as an :class:`IdentityProviderUpdate`, with the same fields set.
        """
        return IdentityProviderUpdate.model_validate(self.model_dump(exclude={"step_up"}, exclude_unset=True))


class IdentityProviderRead(IdentityProviderBase):
    """Represents an identity provider with decrypted client credentials.

    Inherits from:
        IdentityProviderBase

    Attributes:
        id (uuid.UUID): Unique identifier of the identity provider.
        client_id (str | None): The client ID for the provider, decrypted.
        icon_uploaded (bool): Whether an uploaded icon is shown instead of ``icon``.
        created_at (datetime): Timestamp when the identity provider was created.
        updated_at (datetime): Timestamp when the identity provider was last updated.
        version (int): Optimistic-concurrency counter, also sent as the ETag.
        has_linked_users (bool): Whether users are linked to the provider; while they are, its slug, client ID,
            provider type, issuer and endpoints cannot change.

    Config:
        model_config (ConfigDict): Pydantic model configuration to enable attribute-based initialization,
            forbid extra fields, and validate assignment.

    Methods:
        decrypt_client_id():
            Decrypts the `client_id` attribute after loading from the database.

                IdentityProviderRead: The instance with the decrypted `client_id`.
    """

    id: uuid.UUID
    client_id: StrictStr | None = Field(default=None, min_length=1, max_length=512)
    icon_uploaded: StrictBool = Field(default=False, description="Whether an uploaded icon is shown instead of icon")
    created_at: datetime
    updated_at: datetime
    version: StrictInt = Field(
        default=1,
        ge=1,
        description="Optimistic-concurrency counter, also sent as the ETag",
    )
    has_linked_users: StrictBool = Field(
        default=False,
        description=(
            "Whether users are linked to the provider. While they are, the slug, client_id, provider_type, "
            "issuer_url, authorization_endpoint, token_endpoint and userinfo_endpoint cannot change"
        ),
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
        id (uuid.UUID): Unique identifier of the identity provider.
        name (str): Display name of the identity provider.
        slug (str): URL-friendly unique identifier for the provider.
        icon (str | None): URL or path to the provider's icon image.
        icon_uploaded (bool): Whether an uploaded icon is shown instead of ``icon``.

    Config:
        model_config (dict): Pydantic model configuration to allow population from ORM attributes.
    """

    id: uuid.UUID
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
        provider_type (ProviderType): Protocol of the identity provider ('oidc' or 'oauth2').
        link_by_email (bool): Whether a sign-in links to the local account with the same email.
        sync_email (bool): Whether the verified email is synced on each login.
        issuer_url (str | None): URL of the identity provider's issuer, if applicable.
        scopes (str): Scopes required for authentication.
        icon (str | None): URL or path to the icon representing the identity provider.
        user_mapping (Dict[str, Any] | None): Mapping configuration for user attributes.
        description (str): Description of this template.
        configuration_notes (str | None): Setup instructions for this identity provider.
    """

    template_id: StrictStr = Field(..., description="Template identifier (e.g., 'keycloak', 'authentik')")
    name: StrictStr
    provider_type: idp_constants.ProviderType
    issuer_url: StrictStr | None = None
    link_by_email: StrictBool = False
    sync_email: StrictBool = False
    scopes: StrictStr
    icon: StrictStr | None = None
    user_mapping: dict[str, Any] | None = None
    description: StrictStr = Field(..., description="Description of this template")
    configuration_notes: StrictStr | None = Field(default=None, description="Setup instructions for this IdP")


class StepUpStartRequest(BaseModel):
    """Start a step-up re-authentication with a linked identity provider.

    Attributes:
        code_challenge: S256 challenge of a PKCE verifier the browser keeps until it sends the sensitive request.
        action: The sensitive operation the step-up authorises.
        redirect: Relative frontend path the provider's callback returns to.
    """

    code_challenge: StrictStr = Field(..., min_length=43, max_length=128, description="PKCE S256 challenge")
    action: idp_constants.StepUpAction = Field(..., description="Sensitive operation the step-up authorises")
    redirect: StrictStr = Field(
        ...,
        min_length=1,
        max_length=oauth_state_constants.REDIRECT_MAX_LENGTH,
        description="Relative path to return to",
    )

    model_config = ConfigDict(extra="forbid")


class BrowserFlowStartRead(BaseModel):
    """Where to send the browser to start a link or step-up sign-in with an identity provider.

    Attributes:
        authorization_url: The identity provider's authorization URL.
    """

    authorization_url: StrictStr = Field(..., description="Identity provider authorization URL")


#: One page of the configured identity providers.
IdentityProviderPage = core_pagination.Page[IdentityProviderRead]

#: One page of the enabled identity providers, public fields only.
IdentityProviderPublicPage = core_pagination.Page[IdentityProviderPublicRead]
