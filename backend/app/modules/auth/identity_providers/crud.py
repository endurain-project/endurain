"""CRUD operations for identity providers."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.decorators as core_decorators
import core.logger as core_logger
import modules.auth.identity_providers.links.crud as auth_identity_links_crud
import modules.auth.identity_providers.models as idp_models
import modules.auth.identity_providers.schema as idp_schema


@core_decorators.handle_db_errors
def get_identity_provider(idp_id: int, db: Session) -> idp_models.IdentityProvider | None:
    """
    Retrieve an identity provider by its ID.

    Args:
        idp_id: The unique identifier of the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The identity provider if found, otherwise None.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(idp_models.IdentityProvider).where(idp_models.IdentityProvider.id == idp_id)
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_identity_provider_by_slug(slug: str, db: Session) -> idp_models.IdentityProvider | None:
    """
    Retrieve an identity provider by its slug.

    Args:
        slug: The unique slug identifier for the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The identity provider if found, otherwise None.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(idp_models.IdentityProvider).where(idp_models.IdentityProvider.slug == slug)
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_all_identity_providers(db: Session) -> list[idp_models.IdentityProvider]:
    """
    Retrieve all identity providers ordered by name.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of identity provider objects (empty list if none exist).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(idp_models.IdentityProvider).order_by(idp_models.IdentityProvider.name)
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_identity_providers_by_ids(
    idp_ids: list[int],
    db: Session,
) -> list[idp_models.IdentityProvider]:
    """
    Retrieve multiple identity providers by their IDs.

    Batch fetch to avoid N+1 query problems when enriching user
    identity provider links.

    Args:
        idp_ids: List of identity provider IDs to fetch.
        db: SQLAlchemy database session.

    Returns:
        List of IdentityProvider objects matching the IDs.

    Raises:
        HTTPException: If a database error occurs.
    """
    if not idp_ids:
        return []

    stmt = select(idp_models.IdentityProvider).where(idp_models.IdentityProvider.id.in_(idp_ids))
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def get_enabled_identity_providers(db: Session) -> list[idp_models.IdentityProvider]:
    """
    Retrieve all enabled identity providers ordered by name.

    Args:
        db: SQLAlchemy database session.

    Returns:
        List of enabled IdentityProvider objects.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        select(idp_models.IdentityProvider)
        .where(idp_models.IdentityProvider.enabled.is_(True))
        .order_by(idp_models.IdentityProvider.name)
    )
    return list(db.execute(stmt).scalars().all())


@core_decorators.handle_db_errors
def create_identity_provider(idp_data: idp_schema.IdentityProviderCreate, db: Session) -> idp_models.IdentityProvider:
    """
    Create a new identity provider.

    Encrypts client_id and client_secret before persistence and stores
    the slug in lowercase to keep it case-insensitive.

    Args:
        idp_data: The data required to create the identity provider.
        db: SQLAlchemy database session.

    Returns:
        The newly created identity provider instance.

    Raises:
        HTTPException: 409 if the slug already exists, 500 on database
            errors.
    """
    slug = idp_data.slug.lower()

    # Check if slug already exists
    existing = get_identity_provider_by_slug(slug, db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Identity provider with slug '{slug}' already exists",
        )

    # Encrypt sensitive fields
    encrypted_client_id = core_cryptography.encrypt_token_fernet(idp_data.client_id)
    encrypted_client_secret = core_cryptography.encrypt_token_fernet(idp_data.client_secret)

    db_idp = idp_models.IdentityProvider(
        name=idp_data.name,
        slug=slug,
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

    core_logger.print_to_log(f"Created identity provider: {db_idp.name} (ID: {db_idp.id})", "info")

    return db_idp


@core_decorators.handle_db_errors
def update_identity_provider(
    idp_id: int, idp_data: idp_schema.IdentityProviderUpdate, db: Session
) -> idp_models.IdentityProvider:
    """
    Update an existing identity provider.

    Encrypts updated client_id / client_secret values and normalizes the
    slug to lowercase before persistence.

    Args:
        idp_id: The ID of the identity provider to update.
        idp_data: The data to update the identity provider with.
        db: SQLAlchemy database session.

    Returns:
        The updated identity provider instance.

    Raises:
        HTTPException: 404 if the provider is not found, 409 if the new
            slug conflicts with an existing provider, 500 on database
            errors.
    """
    db_idp = get_identity_provider(idp_id, db)
    if not db_idp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found",
        )

    update_data = idp_data.model_dump(exclude_unset=True)

    # Normalize slug and check for conflicts
    if update_data.get("slug"):
        new_slug = update_data["slug"].lower()
        update_data["slug"] = new_slug
        if new_slug != db_idp.slug:
            existing = get_identity_provider_by_slug(new_slug, db)
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(f"Identity provider with slug '{new_slug}' already exists"),
                )

    # Encrypt sensitive fields if present
    if update_data.get("client_id"):
        update_data["client_id"] = core_cryptography.encrypt_token_fernet(update_data["client_id"])
    if update_data.get("client_secret"):
        update_data["client_secret"] = core_cryptography.encrypt_token_fernet(update_data["client_secret"])

    for field, value in update_data.items():
        setattr(db_idp, field, value)

    db.commit()
    db.refresh(db_idp)

    core_logger.print_to_log(f"Updated identity provider: {db_idp.name} (ID: {db_idp.id})", "info")

    return db_idp


@core_decorators.handle_db_errors
def delete_identity_provider(idp_id: int, db: Session) -> None:
    """
    Delete an identity provider by ID.

    Refuses deletion when one or more users are still linked to the
    provider.

    Args:
        idp_id: The ID of the identity provider to delete.
        db: SQLAlchemy database session.

    Raises:
        HTTPException: 404 if the provider is not found, 409 if users
            are linked to the provider, 500 on database errors.
    """
    db_idp = get_identity_provider(idp_id, db)
    if not db_idp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found",
        )

    # Check if any users are linked to this provider
    db_user_idp = auth_identity_links_crud.check_user_identity_providers_by_idp_id(idp_id, db)
    if db_user_idp:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete identity provider with linked users",
        )

    db.delete(db_idp)
    db.commit()

    core_logger.print_to_log(f"Deleted identity provider: {db_idp.name} (ID: {idp_id})", "info")
