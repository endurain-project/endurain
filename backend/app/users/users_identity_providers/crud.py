"""CRUD operations for user identity providers."""

from datetime import datetime, timezone
from sqlalchemy import exists, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

import core.decorators as core_decorators
import users.users_identity_providers.models as user_idp_models


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
    stmt = select(
        exists().where(user_idp_models.UsersIdentityProvider.idp_id == idp_id)
    )
    return db.execute(stmt).scalar() or False


@core_decorators.handle_db_errors
def get_user_identity_providers_by_user_id(
    user_id: int,
    db: Session,
) -> list[user_idp_models.UsersIdentityProvider]:
    """
    Retrieve all identity provider links for a user.

    Args:
        user_id: The ID of the user.
        db: SQLAlchemy database session.

    Returns:
        List of UsersIdentityProvider objects linked to the user.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(user_idp_models.UsersIdentityProvider).where(
        user_idp_models.UsersIdentityProvider.user_id == user_id
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_user_identity_provider_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> user_idp_models.UsersIdentityProvider | None:
    """
    Retrieve identity provider link for a user.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The UsersIdentityProvider instance if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(user_idp_models.UsersIdentityProvider).where(
        user_idp_models.UsersIdentityProvider.user_id == user_id,
        user_idp_models.UsersIdentityProvider.idp_id == idp_id,
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_user_identity_provider_by_subject_and_idp_id(
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> user_idp_models.UsersIdentityProvider | None:
    """
    Retrieve identity provider link by IdP and subject.

    Args:
        idp_id: The ID of the identity provider.
        idp_subject: The subject identifier from the IdP.
        db: SQLAlchemy database session.

    Returns:
        The matching UsersIdentityProvider record if found, None
        otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    stmt = select(user_idp_models.UsersIdentityProvider).where(
        user_idp_models.UsersIdentityProvider.idp_id == idp_id,
        user_idp_models.UsersIdentityProvider.idp_subject == idp_subject,
    )
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def create_user_identity_provider(
    user_id: int,
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> user_idp_models.UsersIdentityProvider:
    """
    Create a link between a user and an identity provider.

    Args:
        user_id: The ID of the user to link.
        idp_id: The ID of the identity provider.
        idp_subject: The subject identifier from the IdP.
        db: SQLAlchemy database session.

    Returns:
        The newly created UsersIdentityProvider link object.

    Raises:
        HTTPException: 409 error if link already exists.
        HTTPException: 500 error if database operation fails.
    """
    db_link = user_idp_models.UsersIdentityProvider(
        user_id=user_id,
        idp_id=idp_id,
        idp_subject=idp_subject,
        last_login=func.now(),
    )
    db.add(db_link)
    db.commit()
    db.refresh(db_link)
    return db_link


@core_decorators.handle_db_errors
def update_user_identity_provider_last_login(
    user_id: int,
    idp_id: int,
    db: Session,
) -> user_idp_models.UsersIdentityProvider | None:
    """
    Update last login timestamp for a user-IdP link.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The updated UsersIdentityProvider link if found, None
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
        db_link.last_login = datetime.now(timezone.utc)
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
) -> user_idp_models.UsersIdentityProvider | None:
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
        The updated UsersIdentityProvider link if found, None
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
        db_link.idp_refresh_token_updated_at = datetime.now(timezone.utc)
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
