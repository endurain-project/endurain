"""HTTP routes for managing identity providers (admin only)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security, status
from sqlalchemy.orm import Session

import core.database as core_database
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.utils as idp_utils
import modules.users.users.schema as users_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[idp_schema.IdentityProvider],
    status_code=status.HTTP_200_OK,
)
async def list_identity_providers(
    _check_scopes: Annotated[
        users_schema.UsersRead,
        Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[idp_schema.IdentityProvider]:
    """
    Retrieve a list of all identity providers.

    Args:
        db: SQLAlchemy database session dependency.
        _check_scopes: Authenticated user with the
            'identity_providers:read' scope.

    Returns:
        A list of all configured identity providers.
    """
    return idp_crud.get_all_identity_providers(db)


@router.get(
    "/templates",
    response_model=list[idp_schema.IdentityProviderTemplate],
    status_code=status.HTTP_200_OK,
)
async def list_idp_templates(
    _check_scopes: Annotated[
        users_schema.UsersRead,
        Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"]),
    ],
) -> list[idp_schema.IdentityProviderTemplate]:
    """
    Get the list of pre-configured IdP templates (admin only).

    Args:
        _check_scopes: Authenticated user with the
            'identity_providers:read' scope.

    Returns:
        A list of identity provider templates.
    """
    return idp_utils.get_idp_templates()


@router.post(
    "",
    response_model=idp_schema.IdentityProvider,
    status_code=status.HTTP_201_CREATED,
)
async def create_identity_provider(
    _check_scopes: Annotated[
        users_schema.UsersRead,
        Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"]),
    ],
    idp_data: idp_schema.IdentityProviderCreate,
    db: Annotated[Session, Depends(core_database.get_db)],
) -> idp_schema.IdentityProvider:
    """
    Create a new identity provider.

    Args:
        idp_data: Data required to create the identity provider.
        db: SQLAlchemy database session dependency.
        _check_scopes: Authenticated user with the
            'identity_providers:write' scope.

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
)
async def update_identity_provider(
    idp_id: int,
    _validate_id: Annotated[Callable, Depends(idp_dependencies.validate_idp_id)],
    _check_scopes: Annotated[
        users_schema.UsersRead,
        Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"]),
    ],
    idp_data: idp_schema.IdentityProviderUpdate,
    db: Annotated[Session, Depends(core_database.get_db)],
) -> idp_schema.IdentityProvider:
    """
    Update an existing identity provider.

    Args:
        idp_id: The unique identifier of the identity provider to update.
        idp_data: The data to update the identity provider with.
        db: SQLAlchemy database session dependency.
        _check_scopes: Authenticated user with the
            'identity_providers:write' scope.

    Returns:
        The updated identity provider.

    Raises:
        HTTPException: 404 if the provider is not found, 409 on slug
            conflict, 500 on database errors.
    """
    return idp_crud.update_identity_provider(idp_id, idp_data, db)


@router.delete("/{idp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_identity_provider(
    idp_id: int,
    _validate_id: Annotated[Callable, Depends(idp_dependencies.validate_idp_id)],
    _check_scopes: Annotated[
        users_schema.UsersRead,
        Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"]),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> None:
    """
    Delete an identity provider by ID.

    Args:
        idp_id: The unique identifier of the identity provider to delete.
        _check_scopes: Authenticated user with the
            'identity_providers:write' scope.
        db: SQLAlchemy database session dependency.

    Raises:
        HTTPException: 404 if the provider is not found, 409 if users
            are still linked to the provider.
    """
    idp_crud.delete_identity_provider(idp_id, db)
