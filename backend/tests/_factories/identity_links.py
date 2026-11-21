"""Identity providers and the links between them and users, for tests on the real database."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import modules.auth.constants as auth_constants
import modules.auth.identity_provider_links.contracts as identity_link_contracts
import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.schema as identity_providers_schema
import modules.auth.identity_providers.token_service as idp_token_service
import modules.auth.sessions.integration_service as sessions_integration
import modules.users.users.schema as users_schema


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


def make_oidc_provider(db: Session, slug: str, issuer_url: str | None, **fields: object) -> uuid.UUID:
    """Stage an enabled OpenID Connect provider that discovers its endpoints from the issuer (flushed, not committed).

    The client id and secret are the ones the loopback provider of the SSO tests accepts.

    Args:
        db: Database session.
        slug: The provider's slug, unique among providers.
        issuer_url: The issuer, whose discovery document names the endpoints.
        **fields: Other provider settings, over the defaults.

    Returns:
        The provider's id.
    """
    values: dict[str, object] = {
        "name": f"Provider {slug}",
        "slug": slug,
        "provider_type": identity_providers_constants.ProviderType.OIDC,
        "enabled": True,
        "issuer_url": issuer_url,
        "client_id": "endurain-client",
        "client_secret": "endurain-secret",
    }
    values.update(fields)
    return identity_providers_crud.create_identity_provider(
        identity_providers_schema.IdentityProviderCreate(**values), db
    ).id


def make_idp_session(
    db: Session,
    user: users_schema.UserRead,
    idp_id: uuid.UUID,
    *,
    issues_refresh_token: bool = True,
    id_token: str | None = None,
    sid: str | None = None,
) -> uuid.UUID:
    """Stage a session of the user that signed in through a provider, with the tokens the provider issued.

    The session and the sign-in are made through the sessions module and the token service, which encrypts the tokens
    (flushed, not committed).

    Args:
        db: Database session.
        user: The session's owner.
        idp_id: The provider the user signed in through.
        issues_refresh_token: Whether the provider issued a refresh token (``provider-refresh-token``).
        id_token: The provider's ID token, if any.
        sid: The provider session id the ID token named, if any.

    Returns:
        The session's id.
    """
    session_id = uuid.uuid4()
    sessions_integration.create_session(
        session_id,
        user,
        auth_constants.ClientType.WEB,
        "203.0.113.7",
        "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "refresh-token",
        datetime.now(UTC) + timedelta(days=1),
        db,
        amr=["fed"],
        device_hash=None,
    )
    token_response: dict[str, object] = {"access_token": "at", "expires_in": 3600}
    if issues_refresh_token:
        token_response["refresh_token"] = "provider-refresh-token"
    if id_token is not None:
        token_response["id_token"] = id_token
    idp_token_service.IdpTokenService.store_session_tokens(session_id, user.id, idp_id, token_response, db, idp_sid=sid)
    db.flush()
    return session_id
