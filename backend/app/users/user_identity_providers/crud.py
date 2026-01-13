"""CRUD operations for user identity providers."""

from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func

import core.logger as core_logger
import users.user_identity_providers.models as user_idp_models


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
    try:
        stmt = select(
            exists().where(user_idp_models.UserIdentityProvider.idp_id == idp_id)
        )
        return db.execute(stmt).scalar() or False
    except SQLAlchemyError as db_err:
        core_logger.print_to_log(
            f"Database error checking IdP links: {db_err}",
            "error",
            exc=db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_user_identity_providers_by_user_id(
    user_id: int,
    db: Session,
) -> list[user_idp_models.UserIdentityProvider]:
    """
    Retrieve all identity provider links for a user.

    Args:
        user_id: The ID of the user.
        db: SQLAlchemy database session.

    Returns:
        List of UserIdentityProvider objects linked to the user.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    try:
        stmt = select(user_idp_models.UserIdentityProvider).where(
            user_idp_models.UserIdentityProvider.user_id == user_id
        )
        return list(db.execute(stmt).scalars().all())
    except SQLAlchemyError as db_err:
        core_logger.print_to_log(
            f"Database error fetching user IdP links: {db_err}",
            "error",
            exc=db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_user_identity_provider_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> user_idp_models.UserIdentityProvider | None:
    """
    Retrieve identity provider link for a user.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The UserIdentityProvider instance if found, None otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    try:
        stmt = select(user_idp_models.UserIdentityProvider).where(
            user_idp_models.UserIdentityProvider.user_id == user_id,
            user_idp_models.UserIdentityProvider.idp_id == idp_id,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        core_logger.print_to_log(
            f"Database error fetching IdP link: {db_err}",
            "error",
            exc=db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def get_user_identity_provider_by_subject_and_idp_id(
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> user_idp_models.UserIdentityProvider | None:
    """
    Retrieve identity provider link by IdP and subject.

    Args:
        idp_id: The ID of the identity provider.
        idp_subject: The subject identifier from the IdP.
        db: SQLAlchemy database session.

    Returns:
        The matching UserIdentityProvider record if found, None
        otherwise.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    try:
        stmt = select(user_idp_models.UserIdentityProvider).where(
            user_idp_models.UserIdentityProvider.idp_id == idp_id,
            user_idp_models.UserIdentityProvider.idp_subject == idp_subject,
        )
        return db.execute(stmt).scalar_one_or_none()
    except SQLAlchemyError as db_err:
        core_logger.print_to_log(
            f"Database error fetching IdP link by subject: {db_err}",
            "error",
            exc=db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def create_user_identity_provider(
    user_id: int,
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> user_idp_models.UserIdentityProvider:
    """
    Create a link between a user and an identity provider.

    Args:
        user_id: The ID of the user to link.
        idp_id: The ID of the identity provider.
        idp_subject: The subject identifier from the IdP.
        db: SQLAlchemy database session.

    Returns:
        The newly created UserIdentityProvider link object.

    Raises:
        HTTPException: 409 error if link already exists.
        HTTPException: 500 error if database operation fails.
    """
    try:
        db_link = user_idp_models.UserIdentityProvider(
            user_id=user_id,
            idp_id=idp_id,
            idp_subject=idp_subject,
            last_login=func.now(),
        )
        db.add(db_link)
        db.commit()
        db.refresh(db_link)
        return db_link
    except SQLAlchemyError as db_err:
        db.rollback()
        core_logger.print_to_log(
            f"Database error creating IdP link: {db_err}",
            "error",
            exc=db_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred",
        ) from db_err


def update_user_identity_provider_last_login(
    user_id: int,
    idp_id: int,
    db: Session,
) -> user_idp_models.UserIdentityProvider | None:
    """
    Update last login timestamp for a user-IdP link.

    Args:
        user_id: The ID of the user.
        idp_id: The ID of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The updated UserIdentityProvider link if found, None
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
        try:
            db_link.last_login = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_link)
        except SQLAlchemyError as db_err:
            db.rollback()
            core_logger.print_to_log(
                f"Database error updating last login: {db_err}",
                "error",
                exc=db_err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred",
            ) from db_err
    else:
        core_logger.print_to_log(
            f"IdP link not found for user {user_id}, idp {idp_id}",
            "warning",
        )
    return db_link


def store_user_identity_provider_tokens(
    user_id: int,
    idp_id: int,
    encrypted_refresh_token: str,
    access_token_expires_at: datetime,
    db: Session,
) -> user_idp_models.UserIdentityProvider | None:
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
        The updated UserIdentityProvider link if found, None
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
        try:
            db_link.idp_refresh_token = encrypted_refresh_token
            db_link.idp_access_token_expires_at = access_token_expires_at
            db_link.idp_refresh_token_updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(db_link)
        except SQLAlchemyError as db_err:
            db.rollback()
            core_logger.print_to_log(
                f"Database error storing IdP tokens: {db_err}",
                "error",
                exc=db_err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred",
            ) from db_err
    else:
        core_logger.print_to_log(
            f"IdP link not found for user {user_id}, "
            f"idp {idp_id} when storing tokens",
            "warning",
        )
    return db_link


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
        try:
            db_link.idp_refresh_token = None
            db_link.idp_access_token_expires_at = None
            db_link.idp_refresh_token_updated_at = None
            db.commit()
            return True
        except SQLAlchemyError as db_err:
            db.rollback()
            core_logger.print_to_log(
                f"Database error clearing IdP tokens: {db_err}",
                "error",
                exc=db_err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred",
            ) from db_err
    else:
        core_logger.print_to_log(
            f"IdP link not found for user {user_id}, "
            f"idp {idp_id} when clearing tokens",
            "warning",
        )
    return False


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
        try:
            # Clear sensitive data first (defense in depth)
            db_link.idp_refresh_token = None
            db_link.idp_access_token_expires_at = None
            db_link.idp_refresh_token_updated_at = None
            db.commit()

            # Then delete the link
            db.delete(db_link)
            db.commit()
            return True
        except SQLAlchemyError as db_err:
            db.rollback()
            core_logger.print_to_log(
                f"Database error deleting IdP link: {db_err}",
                "error",
                exc=db_err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred",
            ) from db_err
    else:
        core_logger.print_to_log(
            f"IdP link not found for user {user_id}, idp {idp_id} when deleting",
            "warning",
        )
    return False
