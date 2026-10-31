"""Admin routes for identity-provider configuration."""

from fastapi import APIRouter, Request, Response, Security, UploadFile, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.file_uploads as core_file_uploads
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.icon_service as idp_icon_service
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.identity_providers.schema as idp_schema

router = APIRouter()


@router.get(
    "",
    response_model=list[idp_schema.IdentityProviderRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
def list_identity_providers(
    db: core_dependencies.DbSession,
) -> list[idp_schema.IdentityProviderRead]:
    """Retrieve a list of all identity providers.

    Args:
        db: SQLAlchemy database session dependency.

    Returns:
        A list of all configured identity providers.
    """
    return idp_provider_service.list_identity_providers(db)


@router.get(
    "/templates",
    response_model=list[idp_schema.IdentityProviderTemplateRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
def list_idp_templates() -> list[idp_schema.IdentityProviderTemplateRead]:
    """Get the list of pre-configured IdP templates (admin only).

    Returns:
        A list of identity provider templates.
    """
    return idp_provider_service.get_idp_templates()


@router.post(
    "",
    response_model=idp_schema.IdentityProviderRead,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Create a new identity provider.\n\n"
        "Args:\n"
        "    idp_data: Data required to create the identity provider.\n"
        "    db: SQLAlchemy database session dependency.\n"
        "    request: Incoming request.\n"
        "\n"
        "Returns:\n"
        "    The newly created identity provider.\n\n"
        "Raises:\n"
        "    HTTPException: 409 if the slug already exists, 500 on\n"
        "        database errors."
    ),
    responses={
        status.HTTP_201_CREATED: {
            "headers": {
                "ETag": {
                    "description": "The version of this identity provider",
                    "schema": {"type": "string"},
                }
            }
        }
    },
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_identity_provider(
    idp_data: idp_schema.IdentityProviderCreate,
    request: Request,
    db: core_dependencies.DbSession,
    response: Response,
) -> idp_schema.IdentityProviderRead:
    """Create a new identity provider.

    Args:
        idp_data: Data required to create the identity provider.
        db: SQLAlchemy database session dependency.
        request: Incoming request.
        response: The response, which carries the new ETag.

    Returns:
        The newly created identity provider.

    Raises:
        HTTPException: 409 if the slug already exists, 500 on
            database errors.
    """
    provider = idp_provider_service.create_identity_provider(idp_data, db)
    core_etag.set_etag(response, provider.version)
    return provider


@router.put(
    "/{idp_id}",
    response_model=idp_schema.IdentityProviderRead,
    description=(
        "Update an existing identity provider.\n\n"
        "Args:\n"
        "    idp_id: The unique identifier of the identity provider to update.\n"
        "    idp_data: The data to update the identity provider with.\n"
        "    db: SQLAlchemy database session dependency.\n"
        "    request: Incoming request.\n"
        "\n"
        "Returns:\n"
        "    The updated identity provider.\n\n"
        "Raises:\n"
        "    HTTPException: 404 if the provider is not found, 409 on slug\n"
        "        conflict, 500 on database errors."
    ),
    responses={
        status.HTTP_200_OK: {
            "headers": {
                "ETag": {
                    "description": "The new version of this identity provider",
                    "schema": {"type": "string"},
                }
            }
        },
        status.HTTP_412_PRECONDITION_FAILED: {"description": "The identity provider has changed"},
        status.HTTP_428_PRECONDITION_REQUIRED: {"description": "If-Match is required"},
    },
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_identity_provider(
    idp_id: core_dependencies.PositiveId,
    idp_data: idp_schema.IdentityProviderUpdate,
    request: Request,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> idp_schema.IdentityProviderRead:
    """Update an existing identity provider.

    Args:
        idp_id: The unique identifier of the identity provider to update.
        idp_data: The data to update the identity provider with.
        db: SQLAlchemy database session dependency.
        request: Incoming request.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition the client read.

    Returns:
        The updated identity provider.

    Raises:
        HTTPException: 404 if the provider is not found, 409 on slug conflict,
            412 if the provider changed, or 500 on database errors.
    """
    provider = idp_provider_service.update_identity_provider(idp_id, idp_data, db, if_match=if_match)
    core_etag.set_etag(response, provider.version)
    return provider


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
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
) -> None:
    """Delete an identity provider by ID.

    Args:
        idp_id: The unique identifier of the identity provider to delete.
        request: Incoming request.
        if_match: The ``If-Match`` precondition.
        db: SQLAlchemy database session dependency.
        storage: The platform storage provider.

    Raises:
        HTTPException: 404 if the provider is not found, 409 if users
            are still linked to the provider, 412 if the provider changed
            since the client read it.
    """
    idp_provider_service.delete_identity_provider(idp_id, storage, db, if_match=if_match)


@router.post(
    "/{idp_id}/icon",
    response_model=idp_schema.IdentityProviderIconRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def upload_identity_provider_icon(
    idp_id: core_dependencies.PositiveId,
    request: Request,
    file: UploadFile,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> idp_schema.IdentityProviderIconRead:
    """Upload the icon an identity provider shows on the login page.

    Requires admin authentication with identity_providers:write scope. The icon replaces any custom icon URL
    until it is removed.

    Args:
        idp_id: The identity provider the icon belongs to.
        request: Incoming request.
        file: The image to upload (PNG, JPEG, GIF or WebP).
        storage: The platform storage provider.
        db: SQLAlchemy database session dependency.

    Returns:
        The provider version that identifies the stored icon.

    Raises:
        NotFoundError: 404 if the provider is not found.
        PayloadTooLargeError: 413 if the image is larger than the icon cap.
    """
    data = core_file_uploads.read_validated_upload_sync(file, kind=core_file_uploads.UploadKind.IMAGE)
    return idp_schema.IdentityProviderIconRead(version=idp_icon_service.upload_icon(idp_id, data, storage, db))


@router.delete(
    "/{idp_id}/icon",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_identity_provider_icon(
    idp_id: core_dependencies.PositiveId,
    request: Request,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> None:
    """Remove the uploaded icon of an identity provider.

    Requires admin authentication with identity_providers:write scope.

    Args:
        idp_id: The identity provider the icon belongs to.
        request: Incoming request.
        storage: The platform storage provider.
        db: SQLAlchemy database session dependency.

    Raises:
        NotFoundError: 404 if the provider is not found.
    """
    idp_icon_service.delete_icon(idp_id, storage, db)
