"""Identity providers and the links between them and users, for tests on the real database."""

import uuid

from sqlalchemy.orm import Session

import modules.auth.identity_provider_links.contracts as identity_link_contracts
import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.schema as identity_providers_schema


def make_identity_provider(db: Session, slug: str) -> uuid.UUID:
    """Stage an enabled OAuth2 identity provider through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        slug: The provider's slug, unique among providers.

    Returns:
        The provider's id.
    """
    created = identity_providers_crud.create_identity_provider(
        identity_providers_schema.IdentityProviderCreate(
            name=f"Provider {slug}",
            slug=slug,
            provider_type=identity_providers_constants.ProviderType.OAUTH2,
            enabled=True,
            scopes="profile email",
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint="https://idp.example.com/userinfo",
            client_id="client-id",
            client_secret="client-secret",
        ),
        db,
    )
    return created.id


def make_identity_link(
    db: Session, user_id: uuid.UUID, idp_id: uuid.UUID, subject: str
) -> identity_link_contracts.IdentityLinkRead:
    """Stage a link between a user and a provider through the module's create function (flushed, not committed).

    Args:
        db: Database session.
        user_id: The linked user.
        idp_id: The provider.
        subject: The user's subject at the provider.

    Returns:
        The staged link.
    """
    return identity_links_crud.create_user_identity_provider(user_id, idp_id, subject, db)
