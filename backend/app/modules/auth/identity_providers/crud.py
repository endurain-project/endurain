"""Persistence operations for identity providers."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

import core.cryptography as core_cryptography
import core.database as core_database
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.key_rotation as core_key_rotation
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.identity_providers.models as identity_provider_models
import modules.auth.identity_providers.schema as identity_provider_schema
import modules.auth.identity_providers.serializers as identity_provider_serializers
import modules.auth.identity_providers.utils as idp_utils


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


def get_identity_provider_by_issuer(
    issuer_url: str, db: Session, *, exclude_id: int | None = None
) -> identity_provider_contracts.IdentityProviderState | None:
    """Return a provider whose issuer URL equals the given one, apart from trailing slashes.

    Args:
        issuer_url: The issuer URL to look up.
        db: Database session.
        exclude_id: A provider row to leave out of the lookup.

    Returns:
        A matching provider state, or ``None`` when no other provider uses the issuer.
    """
    normalized = idp_utils.normalize_issuer_url(issuer_url)
    query = select(identity_provider_models.IdentityProvider).where(
        func.rtrim(identity_provider_models.IdentityProvider.issuer_url, "/") == normalized
    )
    if exclude_id is not None:
        query = query.where(identity_provider_models.IdentityProvider.id != exclude_id)
    row = db.execute(query.limit(1)).scalar_one_or_none()
    return identity_provider_serializers.to_state(row) if row is not None else None


def get_identity_providers_page(
    db: Session,
    *,
    enabled_only: bool,
    limit: int,
    offset: int,
) -> list[identity_provider_contracts.IdentityProviderState]:
    """Return one window of providers ordered by name, with the id as tiebreak."""
    model = identity_provider_models.IdentityProvider
    stmt = select(model).order_by(model.name, model.id).limit(limit).offset(offset)
    if enabled_only:
        stmt = stmt.where(model.enabled.is_(True))
    rows = db.execute(stmt).scalars()
    return [identity_provider_serializers.to_state(row) for row in rows]


def count_identity_providers(db: Session, *, enabled_only: bool) -> int:
    """Return how many providers exist, or how many are enabled."""
    model = identity_provider_models.IdentityProvider
    stmt = select(func.count(model.id))
    if enabled_only:
        stmt = stmt.where(model.enabled.is_(True))
    return db.execute(stmt).scalar_one()


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


def _flush_refusing_shared_issuer(
    db: Session, new_row: identity_provider_models.IdentityProvider | None = None
) -> None:
    """Flush staged provider changes in a savepoint, turning the issuer unique-index violation into a refusal.

    The service checks for a shared issuer first, but two concurrent writes can both pass that check, so the unique
    index decides. Rolling the session back is the transaction owner's job.

    Args:
        db: Database session.
        new_row: A provider row to add before flushing, or ``None`` when the changes are already staged.

    Raises:
        IssuerInUseError: When the flush violates the unique index on the issuer.
    """
    try:
        with db.begin_nested():
            if new_row is not None:
                db.add(new_row)
            db.flush()
    except IntegrityError as err:
        if _is_shared_issuer(err):
            raise core_exceptions.IssuerInUseError() from err
        raise


def _is_shared_issuer(err: IntegrityError) -> bool:
    """Whether an integrity error is the unique index on the normalized issuer.

    Args:
        err: The integrity error raised by the flush.

    Returns:
        True for the issuer index violation. SQLite names no constraint, so its error text is searched for the
        index name instead.
    """
    constraint = core_database.violated_constraint(err)
    if constraint is not None:
        return constraint == identity_provider_models.ISSUER_UNIQUE_INDEX
    return identity_provider_models.ISSUER_UNIQUE_INDEX in str(err.orig)


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
        icon_uploaded=False,
        auto_create_users=data.auto_create_users,
        link_by_email=data.link_by_email,
        sync_user_info=data.sync_user_info,
        sync_email=data.sync_email,
        user_mapping=data.user_mapping,
    )
    _flush_refusing_shared_issuer(db, row)
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
    _flush_refusing_shared_issuer(db)
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


def get_ids_with_icon(idp_ids: list[int], db: Session) -> set[int]:
    """Return which of the given providers have an uploaded icon.

    Args:
        idp_ids: The providers to look up.
        db: Database session.

    Returns:
        The ids of the providers that exist and have an uploaded icon.
    """
    stmt = select(identity_provider_models.IdentityProvider.id).where(
        identity_provider_models.IdentityProvider.id.in_(idp_ids),
        identity_provider_models.IdentityProvider.icon_uploaded.is_(True),
    )
    return set(db.execute(stmt).scalars().all())


def set_icon_uploaded(idp_id: int, is_set: bool, db: Session) -> tuple[int, bool] | None:
    """Stage whether a provider has an uploaded icon.

    Args:
        idp_id: The provider to flag.
        is_set: True when an icon is stored.
        db: Database session.

    Returns:
        The provider version the change was staged as, which identifies the icon, and whether the provider had an
        icon before; ``None`` when the row is missing.
    """
    row = db.execute(
        select(identity_provider_models.IdentityProvider)
        .where(identity_provider_models.IdentityProvider.id == idp_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        return None
    had_icon = row.icon_uploaded
    row.icon_uploaded = is_set
    # A replaced icon leaves the flag as it was; flagging it forces the UPDATE that bumps the version,
    # which is the icon's entity tag.
    flag_modified(row, "icon_uploaded")
    db.flush()
    return row.version, had_icon


def stage_reencrypt_batch_providers(after_id: int, limit: int, db: Session) -> core_key_rotation.BatchResult:
    """Stage the re-encryption of up to ``limit`` providers rows after ``after_id`` (flushed, not committed)."""
    model = identity_provider_models.IdentityProvider
    return core_key_rotation.stage_reencrypt_batch(
        model,
        model.id,
        (
            model.client_id,
            model.client_secret,
        ),
        after_id,
        limit,
        db,
    )
