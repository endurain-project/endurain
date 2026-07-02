"""CRUD operations for user identity provider links."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

import auth.identity_providers.links.models as auth_identity_links_models
import core.decorators as core_decorators


@core_decorators.handle_db_errors
def check_user_identity_providers_by_idp_id(
    idp_id: int,
    db: Session,
) -> bool:
    """
    Check if any user links exist for an identity provider.

    Args:
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        True if at least one user is linked, False otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(exists().where(auth_identity_links_models.IdentityLink.idp_id == idp_id))
    return db.execute(stmt).scalar() or False


@core_decorators.handle_db_errors
def get_user_identity_providers_by_user_id(
    user_id: int,
    db: Session,
) -> list[auth_identity_links_models.IdentityLink]:
    """
    Retrieve all identity provider links for a user.

    Args:
        user_id: The ID of the user.
        db: SQLAlchemy database session.

    Returns:
        List of IdentityLink objects linked to the user.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(auth_identity_links_models.IdentityLink).where(
        auth_identity_links_models.IdentityLink.user_id == user_id
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_user_identity_provider_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> auth_identity_links_models.IdentityLink | None:
    """
    Retrieve identity provider link for a user.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The IdentityLink instance if found, None
        otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(auth_identity_links_models.IdentityLink).where(
        auth_identity_links_models.IdentityLink.user_id == user_id,
        auth_identity_links_models.IdentityLink.idp_id == idp_id,
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_user_identity_provider_by_subject_and_idp_id(
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> auth_identity_links_models.IdentityLink | None:
    """
    Retrieve identity provider link by IdP and subject.

    Args:
        idp_id: The ID of the identity provider.
        idp_subject: The subject identifier from the IdP.
        db: SQLAlchemy database session.

    Returns:
        The matching IdentityLink record if found,
        None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(auth_identity_links_models.IdentityLink).where(
        auth_identity_links_models.IdentityLink.idp_id == idp_id,
        auth_identity_links_models.IdentityLink.idp_subject == idp_subject,
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_user_identity_provider(
    user_id: int,
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> auth_identity_links_models.IdentityLink:
    """
    Create a link between a user and an identity provider.

    Args:
        user_id: The ID of the user to link.
        idp_id: The ID of the identity provider.
        idp_subject: The subject identifier from the IdP.
        db: SQLAlchemy database session.

    Returns:
        The newly created IdentityLink link object.

    Raises:
        HTTPException: 409 error if link already exists.
        HTTPException: 500 error if database operation fails.
    """
    db_link = auth_identity_links_models.IdentityLink(
        user_id=user_id,
        idp_id=idp_id,
        idp_subject=idp_subject,
        last_login=func.now(),
    )
    db.add(db_link)
    try:
        db.commit()
    except IntegrityError as err:
        db.rollback()
        raise HTTPException(status_code=409, detail="Identity provider already linked") from err
    db.refresh(db_link)
    return db_link


@core_decorators.handle_db_errors
def update_user_identity_provider_last_login(
    user_id: int,
    idp_id: int,
    db: Session,
) -> auth_identity_links_models.IdentityLink | None:
    """
    Update last login timestamp for a user-IdP link.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The updated IdentityLink link if found, None
        otherwise.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(
        user_id,
        idp_id,
        db,
    )
    if db_link:
        db_link.last_login = datetime.now(UTC)
        db.commit()
        db.refresh(db_link)
    return db_link


@core_decorators.handle_db_errors
def store_user_identity_provider_tokens(
    user_id: int,
    idp_id: int,
    encrypted_refresh_token: str,
    access_token_expires_at: datetime,
    db: Session,
) -> auth_identity_links_models.IdentityLink | None:
    """
    Store encrypted IdP tokens for a user-IdP link.

    Token must be pre-encrypted with Fernet before calling.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        encrypted_refresh_token: Fernet-encrypted refresh token.
        access_token_expires_at: Access token expiry time.
        db: SQLAlchemy database session.

    Returns:
        The updated IdentityLink link if found, None
        otherwise.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(
        user_id,
        idp_id,
        db,
    )
    if db_link:
        db_link.idp_refresh_token = encrypted_refresh_token
        db_link.idp_access_token_expires_at = access_token_expires_at
        db_link.idp_refresh_token_updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(db_link)
    return db_link


@core_decorators.handle_db_errors
def clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> bool:
    """
    Clear IdP refresh token and metadata.

    Called when user logs out, token refresh fails, user unlinks
    IdP, or security requires token invalidation.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        True if token was cleared, False if link not found.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(
        user_id,
        idp_id,
        db,
    )
    if db_link:
        db_link.idp_refresh_token = None
        db_link.idp_access_token_expires_at = None
        db_link.idp_refresh_token_updated_at = None
        db.commit()
        return True
    return False


@core_decorators.handle_db_errors
def delete_user_identity_provider(
    user_id: int,
    idp_id: int,
    db: Session,
) -> bool:
    """
    Delete link between user and identity provider.

    Implements defense-in-depth by clearing sensitive token
    data before deletion.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider to unlink.
        db: SQLAlchemy database session.

    Returns:
        True if link was found and deleted, False otherwise.

    Raises:
        HTTPException: 500 error if database operation fails.
    """
    db_link = get_user_identity_provider_by_user_id_and_idp_id(
        user_id,
        idp_id,
        db,
    )
    if db_link:
        # Clear sensitive data first (defense in depth)
        db_link.idp_refresh_token = None
        db_link.idp_access_token_expires_at = None
        db_link.idp_refresh_token_updated_at = None
        db.commit()

        # Then delete the link
        db.delete(db_link)
        db.commit()
        return True
    return False


@core_decorators.handle_db_errors
def get_identity_link_counts_for_users(
    user_ids: list[int],
    db: Session,
) -> dict[int, int]:
    """
    Return identity provider link count per user in a single query.

    Args:
        user_ids: List of user IDs to count links for.
        db: SQLAlchemy database session.

    Returns:
        Dict mapping user_id to the number of linked IdPs.
        Users with no links are not present in the result (default to 0).

    Raises:
        HTTPException: 500 error if database query fails.
    """
    if not user_ids:
        return {}
    stmt = (
        select(
            auth_identity_links_models.IdentityLink.user_id,
            func.count(auth_identity_links_models.IdentityLink.id).label("cnt"),
        )
        .where(auth_identity_links_models.IdentityLink.user_id.in_(user_ids))
        .group_by(auth_identity_links_models.IdentityLink.user_id)
    )
    rows = db.execute(stmt).all()
    return {row.user_id: row.cnt for row in rows}


@core_decorators.handle_db_errors
def get_user_ids_with_identity_links(db: Session) -> set[int]:
    """
    Return the set of user IDs that have at least one identity-provider link.

    Args:
        db: SQLAlchemy database session.

    Returns:
        Set of user IDs with one or more linked IdPs. Empty when no links exist.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(auth_identity_links_models.IdentityLink.user_id).distinct()
    return set(db.execute(stmt).scalars().all())
