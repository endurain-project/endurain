"""Admin routes for identity-provider configuration."""

from fastapi import APIRouter, Request, Security, status

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.schema as idp_schema

router = APIRouter()


@router.get(
    "",
    response_model=list[idp_schema.IdentityProviderRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
def list_identity_providers(
    db: core_dependencies.DbSession,
    service: idp_dependencies.IdentityProviderService,
) -> list[idp_schema.IdentityProviderRead]:
    """Retrieve a list of all identity providers.

    Args:
        db: SQLAlchemy database session dependency.

        service: Value used by this operation.

    Returns:
        A list of all configured identity providers.
    """
    return service.list_identity_providers(db)


@router.get(
    "/templates",
    response_model=list[idp_schema.IdentityProviderTemplate],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
def list_idp_templates(service: idp_dependencies.IdentityProviderService) -> list[idp_schema.IdentityProviderTemplate]:
    """Get the list of pre-configured IdP templates (admin only).

    Args:
        service: Value used by this operation.

    Returns:
        A list of identity provider templates.
    """
    return service.get_idp_templates()


@router.post(
    "",
    response_model=idp_schema.IdentityProviderRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_identity_provider(
    idp_data: idp_schema.IdentityProviderCreate,
    request: Request,
    db: core_dependencies.DbSession,
    service: idp_dependencies.IdentityProviderService,
) -> idp_schema.IdentityProviderRead:
    """Create a new identity provider.

    Args:
        idp_data: Data required to create the identity provider.
        db: SQLAlchemy database session dependency.

        request: Value used by this operation.
        service: Value used by this operation.

    Returns:
        The newly created identity provider.

    Raises:
        HTTPException: 409 if the slug already exists, 500 on
            database errors.
    """
    return service.create_identity_provider(idp_data, db)


@router.put(
    "/{idp_id}",
    response_model=idp_schema.IdentityProviderRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_identity_provider(
    idp_id: core_dependencies.PositiveId,
    idp_data: idp_schema.IdentityProviderUpdate,
    request: Request,
    db: core_dependencies.DbSession,
    service: idp_dependencies.IdentityProviderService,
) -> idp_schema.IdentityProviderRead:
    """Update an existing identity provider.

    Args:
        idp_id: The unique identifier of the identity provider to update.
        idp_data: The data to update the identity provider with.
        db: SQLAlchemy database session dependency.

        request: Value used by this operation.
        service: Value used by this operation.

    Returns:
        The updated identity provider.

    Raises:
        HTTPException: 404 if the provider is not found, 409 on slug
            conflict, 500 on database errors.
    """
    return service.update_identity_provider(idp_id, idp_data, db)


@router.delete(
    "/{idp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_identity_provider(
    idp_id: core_dependencies.PositiveId,
    request: Request,
    db: core_dependencies.DbSession,
    service: idp_dependencies.IdentityProviderService,
) -> None:
    """Delete an identity provider by ID.

    Args:
        idp_id: The unique identifier of the identity provider to delete.
        db: SQLAlchemy database session dependency.

        request: Value used by this operation.
        service: Value used by this operation.

    Raises:
        HTTPException: 404 if the provider is not found, 409 if users
            are still linked to the provider.
    """
    service.delete_identity_provider(idp_id, db)
