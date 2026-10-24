"""HTTP routes for managing identity providers (admin only)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status

import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.utils as idp_utils

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[idp_schema.IdentityProvider],
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
async def list_identity_providers(
    db: core_dependencies.DbSession,
) -> list[idp_schema.IdentityProvider]:
    """
    Retrieve a list of all identity providers.

    Args:
        db: SQLAlchemy database session dependency.

    Returns:
        A list of all configured identity providers.
    """
    return idp_crud.get_all_identity_providers(db)


@router.get(
    "/templates",
    response_model=list[idp_schema.IdentityProviderTemplate],
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
async def list_idp_templates() -> list[idp_schema.IdentityProviderTemplate]:
    """
    Get the list of pre-configured IdP templates (admin only).

    Args:

    Returns:
        A list of identity provider templates.
    """
    return idp_utils.get_idp_templates()


@router.post(
    "",
    response_model=idp_schema.IdentityProvider,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
async def create_identity_provider(
    idp_data: idp_schema.IdentityProviderCreate,
    db: core_dependencies.DbSession,
) -> idp_schema.IdentityProvider:
    """
    Create a new identity provider.

    Args:
        idp_data: Data required to create the identity provider.
        db: SQLAlchemy database session dependency.

    Returns:
        The newly created identity provider.

    Raises:
        HTTPException: 409 if the slug already exists, 500 on
            database errors.
    """
    return idp_crud.create_identity_provider(idp_data, db)


@router.put(
    "/{idp_id}",
    response_model=idp_schema.IdentityProvider,
    status_code=status.HTTP_200_OK,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
async def update_identity_provider(
    idp_id: int,
    _validate_id: Annotated[Callable, Depends(idp_dependencies.validate_idp_id)],
    idp_data: idp_schema.IdentityProviderUpdate,
    db: core_dependencies.DbSession,
) -> idp_schema.IdentityProvider:
    """
    Update an existing identity provider.

    Args:
        idp_id: The unique identifier of the identity provider to update.
        idp_data: The data to update the identity provider with.
        db: SQLAlchemy database session dependency.

    Returns:
        The updated identity provider.

    Raises:
        HTTPException: 404 if the provider is not found, 409 on slug
            conflict, 500 on database errors.
    """
    return idp_crud.update_identity_provider(idp_id, idp_data, db)


@router.delete(
    "/{idp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
async def delete_identity_provider(
    idp_id: int,
    _validate_id: Annotated[Callable, Depends(idp_dependencies.validate_idp_id)],
    db: core_dependencies.DbSession,
) -> None:
    """
    Delete an identity provider by ID.

    Args:
        idp_id: The unique identifier of the identity provider to delete.
        db: SQLAlchemy database session dependency.

    Raises:
        HTTPException: 404 if the provider is not found, 409 if users
            are still linked to the provider.
    """
    idp_crud.delete_identity_provider(idp_id, db)
