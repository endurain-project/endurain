"""Persistence operations for identity-provider links."""

from datetime import UTC, datetime

from sqlalchemy import CursorResult, delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.contracts as identity_link_contracts
import modules.auth.identity_provider_links.models as identity_link_models
import modules.auth.identity_provider_links.serializers as identity_link_serializers


def check_user_identity_providers_by_idp_id(idp_id: int, db: Session) -> bool:
    """Return whether an identity provider has linked users."""
    statement = select(exists().where(identity_link_models.IdentityLink.idp_id == idp_id))
    return bool(db.execute(statement).scalar())


def get_user_identity_providers_by_user_id(user_id: int, db: Session) -> list[identity_link_contracts.IdentityLinkRead]:
    """Return the user's identity-provider links."""
    statement = select(identity_link_models.IdentityLink).where(identity_link_models.IdentityLink.user_id == user_id)
    rows = db.execute(statement).scalars().all()
    return [identity_link_serializers.to_read_schema(row) for row in rows]


def get_user_identity_provider_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead | None:
    """Return a link for a user and identity provider."""
    statement = select(identity_link_models.IdentityLink).where(
        identity_link_models.IdentityLink.user_id == user_id,
        identity_link_models.IdentityLink.idp_id == idp_id,
    )
    row = db.execute(statement).scalar_one_or_none()
    return identity_link_serializers.to_read_schema(row) if row is not None else None


def get_user_identity_provider_by_subject_and_idp_id(
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead | None:
    """Return a link matching an identity provider and subject."""
    statement = select(identity_link_models.IdentityLink).where(
        identity_link_models.IdentityLink.idp_id == idp_id,
        identity_link_models.IdentityLink.idp_subject == idp_subject,
    )
    row = db.execute(statement).scalar_one_or_none()
    return identity_link_serializers.to_read_schema(row) if row is not None else None


def create_user_identity_provider(
    user_id: int,
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead:
    """Stage a user-to-provider link, translating unique-key races."""
    row = identity_link_models.IdentityLink(
        user_id=user_id,
        idp_id=idp_id,
        idp_subject=idp_subject,
        last_login=func.now(),
    )
    db.flush()
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Identity provider already linked") from err
    return identity_link_serializers.to_read_schema(row)


def update_user_identity_provider_last_login(
    user_id: int,
    idp_id: int,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead | None:
    """Stage an update to a link's last-login timestamp."""
    row = db.execute(
        select(identity_link_models.IdentityLink).where(
            identity_link_models.IdentityLink.user_id == user_id,
            identity_link_models.IdentityLink.idp_id == idp_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.last_login = datetime.now(UTC)
    db.flush()
    return identity_link_serializers.to_read_schema(row)


def store_user_identity_provider_tokens(
    user_id: int,
    idp_id: int,
    encrypted_refresh_token: str,
    access_token_expires_at: datetime,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead | None:
    """Stage encrypted provider-token metadata on a link."""
    row = db.execute(
        select(identity_link_models.IdentityLink).where(
            identity_link_models.IdentityLink.user_id == user_id,
            identity_link_models.IdentityLink.idp_id == idp_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.idp_refresh_token = encrypted_refresh_token
    row.idp_access_token_expires_at = access_token_expires_at
    row.idp_refresh_token_updated_at = datetime.now(UTC)
    db.flush()
    return identity_link_serializers.to_read_schema(row)


def clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> bool:
    """Stage removal of stored provider-token metadata."""
    row = db.execute(
        select(identity_link_models.IdentityLink).where(
            identity_link_models.IdentityLink.user_id == user_id,
            identity_link_models.IdentityLink.idp_id == idp_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    row.idp_refresh_token = None
    row.idp_access_token_expires_at = None
    row.idp_refresh_token_updated_at = None
    db.flush()
    return True


def replace_refresh_token_if_unchanged(
    user_id: int,
    idp_id: int,
    expected_refresh_token: str,
    encrypted_refresh_token: str,
    access_token_expires_at: datetime,
    db: Session,
) -> bool:
    """Stage new provider-token metadata only while the link still holds the token that was read.

    Args:
        user_id: The link's user.
        idp_id: The link's provider.
        expected_refresh_token: The encrypted refresh token the caller read.
        encrypted_refresh_token: The encrypted refresh token to store.
        access_token_expires_at: When the new access token expires.
        db: Database session.

    Returns:
        True when the token was replaced, False when the link holds another one now.
    """
    model = identity_link_models.IdentityLink
    result: CursorResult[object] = db.execute(
        update(model)
        .where(model.user_id == user_id, model.idp_id == idp_id, model.idp_refresh_token == expected_refresh_token)
        .values(
            idp_refresh_token=encrypted_refresh_token,
            idp_access_token_expires_at=access_token_expires_at,
            idp_refresh_token_updated_at=datetime.now(UTC),
        )
    )
    return result.rowcount == 1


def clear_refresh_token_if_unchanged(user_id: int, idp_id: int, expected_refresh_token: str, db: Session) -> bool:
    """Stage removal of provider-token metadata only while the link still holds the token that was read.

    Args:
        user_id: The link's user.
        idp_id: The link's provider.
        expected_refresh_token: The encrypted refresh token the caller read.
        db: Database session.

    Returns:
        True when the token was cleared, False when the link holds another one now.
    """
    model = identity_link_models.IdentityLink
    result: CursorResult[object] = db.execute(
        update(model)
        .where(model.user_id == user_id, model.idp_id == idp_id, model.idp_refresh_token == expected_refresh_token)
        .values(idp_refresh_token=None, idp_access_token_expires_at=None, idp_refresh_token_updated_at=None)
    )
    return result.rowcount == 1


def delete_user_identity_provider(user_id: int, idp_id: int, db: Session) -> bool:
    """Stage deletion of a user's identity-provider link."""
    result = db.execute(
        delete(identity_link_models.IdentityLink).where(
            identity_link_models.IdentityLink.user_id == user_id,
            identity_link_models.IdentityLink.idp_id == idp_id,
        )
    )
    db.flush()
    return bool(result.rowcount)


def get_identity_link_counts_for_users(user_ids: list[int], db: Session) -> dict[int, int]:
    """Return the number of identity-provider links for each matching user."""
    if not user_ids:
        return {}
    statement = (
        select(
            identity_link_models.IdentityLink.user_id,
            func.count(identity_link_models.IdentityLink.id).label("count"),
        )
        .where(identity_link_models.IdentityLink.user_id.in_(user_ids))
        .group_by(identity_link_models.IdentityLink.user_id)
    )
    return {row.user_id: row.count for row in db.execute(statement).all()}
