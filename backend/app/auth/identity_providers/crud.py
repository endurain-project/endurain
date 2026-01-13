"""CRUD operations for identity providers"""

from sqlalchemy.orm import Session
from typing import List
from fastapi import HTTPException, status

import auth.identity_providers.models as idp_models
import auth.identity_providers.schema as idp_schema
import core.cryptography as core_cryptography
import core.logger as core_logger
import users.user_identity_providers.crud as user_identity_providers_crud


def get_identity_provider(
    idp_id: int, db: Session
) -> idp_models.IdentityProvider | None:
    """
    Retrieve an identity provider by its ID from the database.

    Args:
        idp_id (int): The unique identifier of the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        idp_models.IdentityProvider | None: The identity provider object with decrypted client_id if found, otherwise None.

    Raises:
        HTTPException: If an unexpected error occurs during retrieval or decryption.
    """
    try:
        # Get IDP from database
        return (
            db.query(idp_models.IdentityProvider)
            .filter(idp_models.IdentityProvider.id == idp_id)
            .first()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_identity_provider: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_identity_provider_by_slug(
    slug: str, db: Session
) -> idp_models.IdentityProvider | None:
    """
    Retrieve an IdentityProvider object from the database by its slug.

    Args:
        slug (str): The unique slug identifier for the identity provider.
        db (Session): The SQLAlchemy database session.

    Returns:
        idp_models.IdentityProvider | None: The IdentityProvider object if found, with the client_id decrypted; otherwise, None.

    Raises:
        HTTPException: If an unexpected error occurs during the database query or decryption process, raises a 500 Internal Server Error.
    """
    try:
        # Get IDP from database
        return (
            db.query(idp_models.IdentityProvider)
            .filter(idp_models.IdentityProvider.slug == slug)
            .first()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_identity_provider_by_slug: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_all_identity_providers(db: Session) -> List[idp_models.IdentityProvider]:
    """
    Retrieve all identity providers from the database, ordered by name.

    This function queries the database for all IdentityProvider records, decrypts the
    client_id for each provider, and returns the list. If no identity providers are found,
    an empty list is returned. In case of any exception during the process, an error is
    logged and an HTTP 500 Internal Server Error is raised.

    Args:
        db (Session): SQLAlchemy database session.

    Returns:
        List[idp_models.IdentityProvider]: List of identity provider objects with decrypted client_id.

    Raises:
        HTTPException: If an error occurs during the database query or decryption.
    """
    try:
        # Get IDPs from database
        return (
            db.query(idp_models.IdentityProvider)
            .order_by(idp_models.IdentityProvider.name)
            .all()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_all_identity_providers: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_identity_providers_by_ids(
    idp_ids: list[int],
    db: Session,
) -> list[idp_models.IdentityProvider]:
    """
    Retrieve multiple identity providers by their IDs.

    Batch fetch to avoid N+1 query problems when enriching
    user identity provider links.

    Args:
        idp_ids: List of identity provider IDs to fetch.
        db: SQLAlchemy database session.

    Returns:
        List of IdentityProvider objects matching the IDs.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    if not idp_ids:
        return []

    try:
        return (
            db.query(idp_models.IdentityProvider)
            .filter(idp_models.IdentityProvider.id.in_(idp_ids))
            .all()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_identity_providers_by_ids: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_enabled_providers(db: Session) -> list[idp_models.IdentityProvider]:
    """
    Retrieve all enabled identity providers, ordered by name.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of enabled IdentityProvider objects.

    Raises:
        HTTPException: 500 error if database query fails.
    """
    try:
        return (
            db.query(idp_models.IdentityProvider)
            .filter(idp_models.IdentityProvider.enabled == True)
            .order_by(idp_models.IdentityProvider.name)
            .all()
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error in get_enabled_providers: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_identity_provider(
    idp_data: idp_schema.IdentityProviderCreate, db: Session
) -> idp_models.IdentityProvider:
    """
    Creates a new identity provider in the database.
    This function checks if an identity provider with the given slug already exists.
    If it does, it raises an HTTP 409 Conflict exception. Otherwise, it encrypts
    the sensitive fields (client_id and client_secret), creates a new IdentityProvider
    record, commits it to the database, and logs the creation event.
    Args:
        idp_data (idp_schema.IdentityProviderCreate): The data required to create the identity provider.
        db (Session): The SQLAlchemy database session.
    Returns:
        idp_models.IdentityProvider: The newly created identity provider instance.
    Raises:
        HTTPException: If the slug already exists (409 Conflict) or if an internal error occurs (500 Internal Server Error).
    """
    try:
        # Check if slug already exists
        existing = get_identity_provider_by_slug(idp_data.slug, db)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Identity provider with slug '{idp_data.slug}' already exists",
            )

        # Encrypt sensitive fields
        encrypted_client_id = core_cryptography.encrypt_token_fernet(idp_data.client_id)
        encrypted_client_secret = core_cryptography.encrypt_token_fernet(
            idp_data.client_secret
        )

        # Create the identity provider
        db_idp = idp_models.IdentityProvider(
            name=idp_data.name,
            slug=idp_data.slug.lower(),
            provider_type=idp_data.provider_type,
            enabled=idp_data.enabled,
            client_id=encrypted_client_id,
            client_secret=encrypted_client_secret,
            issuer_url=idp_data.issuer_url,
            authorization_endpoint=idp_data.authorization_endpoint,
            token_endpoint=idp_data.token_endpoint,
            userinfo_endpoint=idp_data.userinfo_endpoint,
            jwks_uri=idp_data.jwks_uri,
            scopes=idp_data.scopes,
            icon=idp_data.icon,
            auto_create_users=idp_data.auto_create_users,
            sync_user_info=idp_data.sync_user_info,
            user_mapping=idp_data.user_mapping,
        )

        db.add(db_idp)
        db.commit()
        db.refresh(db_idp)

        core_logger.print_to_log(
            f"Created identity provider: {db_idp.name} (ID: {db_idp.id})", "info"
        )

        return db_idp
    except HTTPException:
        raise
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in create_identity_provider: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def update_identity_provider(
    idp_id: int, idp_data: idp_schema.IdentityProviderUpdate, db: Session
) -> idp_models.IdentityProvider:
    """
    Update an existing identity provider in the database.
    Args:
        idp_id (int): The ID of the identity provider to update.
        idp_data (idp_schema.IdentityProviderUpdate): The data to update the identity provider with.
        db (Session): The SQLAlchemy database session.
    Returns:
        idp_models.IdentityProvider: The updated identity provider instance.
    Raises:
        HTTPException: If the identity provider is not found (404),
                       if the new slug conflicts with an existing provider (409),
                       or if an unexpected error occurs (500).
    """
    try:
        db_idp = get_identity_provider(idp_id, db)
        if not db_idp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity provider not found",
            )

        # Check if slug is being changed and if it conflicts
        if idp_data.slug and idp_data.slug != db_idp.slug:
            existing = get_identity_provider_by_slug(idp_data.slug, db)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Identity provider with slug '{idp_data.slug}' already exists",
                )

        # Update fields
        update_data = idp_data.model_dump(exclude_unset=True)

        # Handle encrypted fields
        if "client_id" in update_data and update_data["client_id"]:
            update_data["client_id"] = core_cryptography.encrypt_token_fernet(
                update_data["client_id"]
            )
        if "client_secret" in update_data and update_data["client_secret"]:
            update_data["client_secret"] = core_cryptography.encrypt_token_fernet(
                update_data["client_secret"]
            )

        for field, value in update_data.items():
            setattr(db_idp, field, value)

        db.commit()
        db.refresh(db_idp)

        core_logger.print_to_log(
            f"Updated identity provider: {db_idp.name} (ID: {db_idp.id})", "info"
        )

        return db_idp
    except HTTPException:
        raise
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in update_identity_provider: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_identity_provider(idp_id: int, db: Session) -> None:
    """
    Deletes an identity provider by its ID if it exists and has no linked users.
    Args:
        idp_id (int): The ID of the identity provider to delete.
        db (Session): The SQLAlchemy database session.
    Raises:
        HTTPException:
            - 404 if the identity provider is not found.
            - 409 if there are users linked to the identity provider.
            - 500 for any other internal server error.
    """
    try:
        # Check if IDP exists
        db_idp = get_identity_provider(idp_id, db)
        if not db_idp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity provider not found",
            )

        # Check if any users are linked to this provider
        db_user_idp = (
            user_identity_providers_crud.check_user_identity_providers_by_idp_id(
                idp_id, db
            )
        )
        if db_user_idp:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete identity provider with linked users",
            )

        db.delete(db_idp)
        db.commit()

        core_logger.print_to_log(
            f"Deleted identity provider: {db_idp.name} (ID: {idp_id})", "info"
        )
    except HTTPException:
        raise
    except Exception as err:
        db.rollback()
        core_logger.print_to_log(
            f"Error in delete_identity_provider: {err}", "error", exc=err
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
