"""Admin routes for identity-provider configuration."""

from fastapi import APIRouter, Request, Response, Security, UploadFile, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.file_uploads as core_file_uploads
import core.location as core_location
import core.middleware_body_limit as core_middleware_body_limit
import core.openapi_contract as core_openapi_contract
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.dependencies as idp_dependencies
import modules.auth.identity_providers.icon_service as idp_icon_service
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.schema as auth_schema

router = APIRouter()


@router.get(
    "",
    response_model=idp_schema.IdentityProviderPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
def list_identity_providers(
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> idp_schema.IdentityProviderPage:
    """Retrieve one page of the configured identity providers.

    Args:
        page: The requested window.
        db: SQLAlchemy database session dependency.

    Returns:
        The page of identity providers, ordered by name.
    """
    return idp_provider_service.list_identity_providers(page, db)


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


@router.get(
    "/{idp_id}",
    response_model=idp_schema.IdentityProviderRead,
    responses={
        status.HTTP_200_OK: {
            "headers": {
                "ETag": {
                    "description": "The version of this identity provider",
                    "schema": {"type": "string"},
                }
            }
        }
    },
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:read"])],
)
def read_identity_provider(
    idp_id: core_dependencies.PositiveId,
    db: core_dependencies.DbSession,
    response: Response,
) -> idp_schema.IdentityProviderRead:
    """Retrieve one identity provider (admin only); its ``ETag`` is the version for ``If-Match``.

    The client secret is write-only and never returned.
    """
    provider = idp_provider_service.get_identity_provider(idp_id, db)
    core_etag.set_etag(response, provider.version)
    return provider


@router.post(
    "",
    response_model=idp_schema.IdentityProviderRead,
    status_code=status.HTTP_201_CREATED,
    description=(
        "Create a new identity provider.\n\n"
        "Needs the administrator's own step-up verification in step_up.\n\n"
        "Args:\n"
        "    idp_data: Data required to create the identity provider, and the step-up.\n"
        "    db: SQLAlchemy database session dependency.\n"
        "    request: Incoming request.\n"
        "\n"
        "Returns:\n"
        "    The newly created identity provider.\n\n"
        "Raises:\n"
        "    HTTPException: 400 if a URL is plain http to a host outside\n"
        "        SSRF_ALLOWED_HOSTS or non-public, 403 if the step-up fails,\n"
        "        409 if the slug or the issuer is already used by another provider,\n"
        "        500 on database errors."
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
    idp_data: idp_schema.IdentityProviderCreateRequest,
    request: Request,
    db: core_dependencies.DbSession,
    response: Response,
    verify_step_up: auth_dependencies.StepUpVerifierDep,
) -> idp_schema.IdentityProviderRead:
    """Create a new identity provider.

    Needs the administrator's own step-up verification in `step_up`, as a rogue provider can claim accounts.

    Args:
        idp_data: Data required to create the identity provider, and the administrator's step-up.
        db: SQLAlchemy database session dependency.
        request: Incoming request.
        response: The response, which carries the new ETag.
        verify_step_up: Verifies the administrator's step-up.

    Returns:
        The newly created identity provider.

    Raises:
        HTTPException: 400 if a URL is plain http to a host outside SSRF_ALLOWED_HOSTS or non-public, 403 if the
            step-up fails, 409 if the slug or the issuer is already used by another provider, 500 on database
            errors.
    """
    provider = idp_provider_service.create_identity_provider(idp_data.to_create(), idp_data.step_up, verify_step_up, db)
    core_location.set_location(response, request, "read_identity_provider", idp_id=provider.id)
    core_etag.set_etag(response, provider.version)
    return provider


@router.patch(
    "/{idp_id}",
    response_model=idp_schema.IdentityProviderRead,
    description=(
        "Update an existing identity provider.\n\n"
        "Needs the administrator's own step-up verification in step_up.\n\n"
        "Args:\n"
        "    idp_id: The unique identifier of the identity provider to update.\n"
        "    idp_data: The data to update the identity provider with, and the step-up.\n"
        "    db: SQLAlchemy database session dependency.\n"
        "    request: Incoming request.\n"
        "\n"
        "Returns:\n"
        "    The updated identity provider.\n\n"
        "Raises:\n"
        "    HTTPException: 400 if a URL is plain http to a host outside\n"
        "        SSRF_ALLOWED_HOSTS or non-public, 403 if the step-up fails,\n"
        "        404 if the provider is not found, 409 on a slug or issuer conflict\n"
        "        or an issuer change while users are linked,\n"
        "        500 on database errors."
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
    idp_data: idp_schema.IdentityProviderUpdateRequest,
    request: Request,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
    oidc: idp_dependencies.OidcClientService,
    verify_step_up: auth_dependencies.StepUpVerifierDep,
) -> idp_schema.IdentityProviderRead:
    """Update an existing identity provider.

    Needs the administrator's own step-up verification in `step_up`, as a rogue provider can claim accounts.

    Args:
        idp_id: The unique identifier of the identity provider to update.
        idp_data: The data to update the identity provider with, and the administrator's step-up.
        db: SQLAlchemy database session dependency.
        request: Incoming request.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition the client read.
        oidc: The identity-provider client, whose cached discovery document for the provider is dropped.
        verify_step_up: Verifies the administrator's step-up.

    Returns:
        The updated identity provider.

    Raises:
        HTTPException: 400 if a URL is plain http to a host outside SSRF_ALLOWED_HOSTS or non-public, 403 if the
            step-up fails, 404 if the provider is not found, 409 on a slug or issuer conflict or an issuer change
            while users are linked, 412 if the provider changed, or 500 on database errors.
    """
    provider = idp_provider_service.update_identity_provider(
        idp_id, idp_data.to_update(), idp_data.step_up, verify_step_up, oidc, db, if_match=if_match
    )
    core_etag.set_etag(response, provider.version)
    return provider


@router.post(
    "/{idp_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_identity_provider(
    idp_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    request: Request,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
    storage: core_dependencies.Storage,
    oidc: idp_dependencies.OidcClientService,
    verify_step_up: auth_dependencies.StepUpVerifierDep,
) -> None:
    """Delete an identity provider by ID.

    Needs the administrator's own step-up verification in `step_up`, as removing a provider can lock out the users
    who sign in through it. A provider with linked users is refused with 409.

    Args:
        idp_id: The unique identifier of the identity provider to delete.
        body: The administrator's step-up verification.
        request: Incoming request.
        if_match: The ``If-Match`` precondition.
        db: SQLAlchemy database session dependency.
        storage: The platform storage provider.
        oidc: The identity-provider client, whose cached discovery document for the provider is dropped.
        verify_step_up: Verifies the administrator's step-up.

    Raises:
        HTTPException: 403 if the step-up fails, 404 if the provider is not found, 409 if users
            are still linked to the provider, 412 if the provider changed
            since the client read it.
    """
    idp_provider_service.delete_identity_provider(
        idp_id, body.step_up, verify_step_up, storage, oidc, db, if_match=if_match
    )


@router.put(
    "/{idp_id}/icon",
    response_model=idp_schema.IdentityProviderIconRead,
    status_code=status.HTTP_201_CREATED,
    responses=core_openapi_contract.replaced_response(idp_schema.IdentityProviderIconRead),
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity_providers:write"])],
    openapi_extra=core_middleware_body_limit.upload_limit(idp_constants.ICON_MAX_BYTES),
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def put_identity_provider_icon(
    idp_id: core_dependencies.PositiveId,
    request: Request,
    file: UploadFile,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
    response: Response,
) -> idp_schema.IdentityProviderIconRead:
    """Set the icon an identity provider shows on the login page.

    Requires admin authentication with identity_providers:write scope. The icon replaces any custom icon URL
    until it is removed. Answers 201 when the provider had no uploaded icon and 200 when it replaced one.

    Args:
        idp_id: The identity provider the icon belongs to.
        request: Incoming request.
        file: The image to upload (JPEG, PNG or WebP).
        storage: The platform storage provider.
        db: SQLAlchemy database session dependency.
        response: The response, whose status is 200 when an icon was replaced.

    Returns:
        The provider version that identifies the stored icon.

    Raises:
        NotFoundError: 404 if the provider is not found.
        PayloadTooLargeError: 413 if the image is larger than the icon cap.
    """
    version, replaced = idp_icon_service.upload_icon(
        idp_id,
        lambda: core_file_uploads.read_validated_upload_sync(file, kind=core_file_uploads.UploadKind.IMAGE),
        storage,
        db,
    )
    if replaced:
        response.status_code = status.HTTP_200_OK
    return idp_schema.IdentityProviderIconRead(version=version)


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
