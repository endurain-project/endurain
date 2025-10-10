from typing import Annotated, List
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Security,
)
from sqlalchemy.orm import Session

import core.database as core_database
import session.security as session_security
import identity_providers.crud as idp_crud
import identity_providers.schema as idp_schema
import identity_providers.utils as idp_utils
import users.user.schema as users_schema


# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=List[idp_schema.IdentityProvider],
    status_code=status.HTTP_200_OK,
)
async def list_identity_providers(
    db: Annotated[Session, Depends(core_database.get_db)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(session_security.check_scopes, scopes=["server_settings:read"]),
    ],
):
    """
    Retrieve a list of all identity providers.

    Args:
        db (Session): SQLAlchemy database session dependency.
        _check_scopes (users_schema.UserRead): The current authenticated user, validated with the required 'server_settings:read' scope.

    Returns:
        List[IdentityProvider]: A list of all identity providers retrieved from the database.
    """
    return idp_crud.get_all_identity_providers(db)


@router.get(
    "/templates",
    response_model=List[idp_schema.IdentityProviderTemplate],
    status_code=status.HTTP_200_OK,
)
async def list_idp_templates(
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(session_security.check_scopes, scopes=["server_settings:read"]),
    ],
):
    """
    Get list of pre-configured IdP templates (admin only).

    Requires 'server_settings:read' permission.
    """
    return idp_utils.get_idp_templates()


@router.get(
    "/{idp_id}",
    response_model=idp_schema.IdentityProvider,
    status_code=status.HTTP_200_OK,
)
async def get_identity_provider(
    idp_id: int,
    db: Annotated[Session, Depends(core_database.get_db)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(session_security.check_scopes, scopes=["server_settings:read"]),
    ],
):
    """
    Retrieve an identity provider by its ID.

    Args:
        idp_id (int): The unique identifier of the identity provider to retrieve.
        db (Session): SQLAlchemy database session dependency.
        _check_scopes (users_schema.UserRead): Dependency to ensure the user has the required scopes ("server_settings:read").

    Raises:
        HTTPException: If the identity provider is not found, raises a 404 Not Found error.

    Returns:
        The identity provider object if found.
    """
    idp = idp_crud.get_identity_provider(idp_id, db)
    if not idp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Identity provider not found"
        )
    return idp


@router.post(
    "", response_model=idp_schema.IdentityProvider, status_code=status.HTTP_201_CREATED
)
async def create_identity_provider(
    idp_data: idp_schema.IdentityProviderCreate,
    db: Annotated[Session, Depends(core_database.get_db)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(session_security.check_scopes, scopes=["server_settings:write"]),
    ],
):
    """
    Creates a new identity provider in the database.

    Args:
        idp_data (idp_schema.IdentityProviderCreate): The data required to create a new identity provider.
        db (Session): The database session dependency.
        _check_scopes (users_schema.UserRead): The authenticated user, validated for the required scopes.

    Returns:
        idp_schema.IdentityProvider: The newly created identity provider object.

    Raises:
        HTTPException: If the user does not have the required permissions or if creation fails.
    """
    return idp_crud.create_identity_provider(idp_data, db)


@router.put(
    "/{idp_id}",
    response_model=idp_schema.IdentityProvider,
    status_code=status.HTTP_200_OK,
)
async def update_identity_provider(
    idp_id: int,
    idp_data: idp_schema.IdentityProviderUpdate,
    db: Annotated[Session, Depends(core_database.get_db)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(session_security.check_scopes, scopes=["server_settings:write"]),
    ],
):
    """
    Update an existing identity provider with new data.

    Args:
        idp_id (int): The unique identifier of the identity provider to update.
        idp_data (idp_schema.IdentityProviderUpdate): The data to update the identity provider with.
        db (Session): SQLAlchemy database session dependency.
        _check_scopes (users_schema.UserRead): Dependency to ensure the user has the required "server_settings:write" scope.

    Returns:
        The updated identity provider object.

    Raises:
        HTTPException: If the identity provider does not exist or the user lacks sufficient permissions.
    """
    return idp_crud.update_identity_provider(idp_id, idp_data, db)


@router.delete("/{idp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_identity_provider(
    idp_id: int,
    db: Annotated[Session, Depends(core_database.get_db)],
    _check_scopes: Annotated[
        users_schema.UserRead,
        Security(session_security.check_scopes, scopes=["server_settings:write"]),
    ],
):
    """
    Deletes an identity provider by its ID.

    Args:
        idp_id (int): The unique identifier of the identity provider to delete.
        db (Session): SQLAlchemy database session dependency.
        _check_scopes (UserRead): Dependency to ensure the user has the required "server_settings:write" scope.

    Raises:
        HTTPException: If the identity provider does not exist or the user lacks sufficient permissions.

    Returns:
        None
    """
    idp_crud.delete_identity_provider(idp_id, db)
