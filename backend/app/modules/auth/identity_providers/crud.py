"""Persistence operations for identity providers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.etag as core_etag
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.models as identity_provider_models
import modules.auth.identity_providers.schema as identity_provider_schema
import modules.auth.identity_providers.serializers as identity_provider_serializers


def get_identity_provider(idp_id: int, db: Session) -> identity_provider_contracts.IdentityProviderState | None:
    """Return a provider state by its id."""
    row = db.execute(
        select(identity_provider_models.IdentityProvider).where(identity_provider_models.IdentityProvider.id == idp_id)
    ).scalar_one_or_none()
    return identity_provider_serializers.to_state(row) if row is not None else None


def get_identity_provider_by_slug(slug: str, db: Session) -> identity_provider_contracts.IdentityProviderState | None:
    """Return a provider state by its slug."""
    row = db.execute(
        select(identity_provider_models.IdentityProvider).where(identity_provider_models.IdentityProvider.slug == slug)
    ).scalar_one_or_none()
    return identity_provider_serializers.to_state(row) if row is not None else None


def get_all_identity_providers(db: Session) -> list[identity_provider_contracts.IdentityProviderState]:
    """Return every provider ordered by name."""
    rows = (
        db.execute(
            select(identity_provider_models.IdentityProvider).order_by(identity_provider_models.IdentityProvider.name)
        )
        .scalars()
        .all()
    )
    return [identity_provider_serializers.to_state(row) for row in rows]


def get_identity_providers_by_ids(
    idp_ids: list[int], db: Session
) -> list[identity_provider_contracts.IdentityProviderState]:
    """Return providers matching a batch of IDs."""
    if not idp_ids:
        return []
    rows = (
        db.execute(
            select(identity_provider_models.IdentityProvider).where(
                identity_provider_models.IdentityProvider.id.in_(idp_ids)
            )
        )
        .scalars()
        .all()
    )
    return [identity_provider_serializers.to_state(row) for row in rows]


def get_enabled_identity_providers(db: Session) -> list[identity_provider_contracts.IdentityProviderState]:
    """Return enabled providers ordered by name."""
    rows = (
        db.execute(
            select(identity_provider_models.IdentityProvider)
            .where(identity_provider_models.IdentityProvider.enabled.is_(True))
            .order_by(identity_provider_models.IdentityProvider.name)
        )
        .scalars()
        .all()
    )
    return [identity_provider_serializers.to_state(row) for row in rows]


def create_identity_provider(
    data: identity_provider_schema.IdentityProviderCreate, db: Session
) -> identity_provider_contracts.IdentityProviderState:
    """Stage a provider row and return its stored state."""
    row = identity_provider_models.IdentityProvider(
        name=data.name,
        slug=data.slug.lower(),
        provider_type=data.provider_type,
        enabled=data.enabled,
        client_id=core_cryptography.encrypt_token_fernet(data.client_id),
        client_secret=core_cryptography.encrypt_token_fernet(data.client_secret),
        issuer_url=data.issuer_url,
        authorization_endpoint=data.authorization_endpoint,
        token_endpoint=data.token_endpoint,
        userinfo_endpoint=data.userinfo_endpoint,
        jwks_uri=data.jwks_uri,
        scopes=data.scopes,
        icon=data.icon,
        auto_create_users=data.auto_create_users,
        sync_user_info=data.sync_user_info,
        user_mapping=data.user_mapping,
    )
    db.add(row)
    db.flush()
    return identity_provider_serializers.to_state(row)


def update_identity_provider(
    idp_id: int,
    data: identity_provider_schema.IdentityProviderUpdate,
    db: Session,
    *,
    if_match: str,
) -> identity_provider_contracts.IdentityProviderState | None:
    """Stage changes to a provider row after checking its version.

    Args:
        idp_id: Identity-provider row to update.
        data: Replacement fields.
        db: Database session.
        if_match: Version tag the client read.

    Returns:
        The stored state, or ``None`` when the row is missing.
    """
    row = db.execute(
        select(identity_provider_models.IdentityProvider).where(identity_provider_models.IdentityProvider.id == idp_id)
    ).scalar_one_or_none()
    if row is None:
        return None
    core_etag.require_if_match(if_match, row.version, "identity provider")
    values = data.model_dump(exclude_unset=True)
    if values.get("slug"):
        values["slug"] = values["slug"].lower()
    for field in ("client_id", "client_secret"):
        if values.get(field):
            values[field] = core_cryptography.encrypt_token_fernet(values[field])
    for field, value in values.items():
        setattr(row, field, value)
    db.flush()
    return identity_provider_serializers.to_state(row)


def identity_provider_exists(idp_id: int, db: Session) -> bool:
    """Return whether an identity-provider row exists.

    Args:
        idp_id: Identity-provider row to check.
        db: Database session.

    Returns:
        Whether the row exists.
    """
    return (
        db.execute(
            select(identity_provider_models.IdentityProvider.id).where(
                identity_provider_models.IdentityProvider.id == idp_id
            )
        ).scalar_one_or_none()
        is not None
    )


def delete_identity_provider(idp_id: int, db: Session, *, if_match: str) -> bool:
    """Stage deletion of a provider row, returning whether it existed.

    Args:
        idp_id: The provider to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition, checked against the very row that is deleted.

    Returns:
        True when the provider existed and its deletion is staged.

    Raises:
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    row = db.execute(
        select(identity_provider_models.IdentityProvider).where(identity_provider_models.IdentityProvider.id == idp_id)
    ).scalar_one_or_none()
    if row is None:
        return False
    core_etag.require_if_match(if_match, row.version, "identity provider")
    db.delete(row)
    db.flush()
    return True
