"""Admin routes for identity-provider configuration."""

from fastapi import APIRouter, Request, Response, Security, UploadFile, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.file_uploads as core_file_uploads
import core.idempotency as core_idempotency
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity-providers:read"])],
)
def list_identity_providers(
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> idp_schema.IdentityProviderPage:
    """Retrieve one page of the configured identity providers."""
    return idp_provider_service.list_identity_providers(page, db)


@router.get(
    "/templates",
    response_model=list[idp_schema.IdentityProviderTemplateRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity-providers:read"])],
)
def list_idp_templates() -> list[idp_schema.IdentityProviderTemplateRead]:
    """Get the list of pre-configured IdP templates (admin only)."""
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity-providers:read"])],
)
def read_identity_provider(
    idp_id: core_dependencies.UuidId,
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
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "A URL field is plain http to a host outside the allowed hosts, or resolves to a "
            "non-public address."
        },
        status.HTTP_201_CREATED: {
            "headers": {
                "ETag": {
                    "description": "The version of this identity provider",
                    "schema": {"type": "string"},
                }
            }
        },
    },
    dependencies=[
        Security(auth_dependencies.check_scopes, scopes=["identity-providers:write"]),
        core_idempotency.Idempotent,
    ],
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
    """
    provider = idp_provider_service.create_identity_provider(idp_data.to_create(), idp_data.step_up, verify_step_up, db)
    core_location.set_location(response, request, "read_identity_provider", idp_id=provider.id)
    core_etag.set_etag(response, provider.version)
    return provider


@router.patch(
    "/{idp_id}",
    response_model=idp_schema.IdentityProviderRead,
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "A URL field is plain http to a host outside the allowed hosts, or resolves to a "
            "non-public address; or `If-Match` is `*`."
        },
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity-providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_identity_provider(
    idp_id: core_dependencies.UuidId,
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity-providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_identity_provider(
    idp_id: core_dependencies.UuidId,
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
    """
    idp_provider_service.delete_identity_provider(
        idp_id, body.step_up, verify_step_up, storage, oidc, db, if_match=if_match
    )


@router.put(
    "/{idp_id}/icon",
    response_model=idp_schema.IdentityProviderIconRead,
    status_code=status.HTTP_201_CREATED,
    responses=core_openapi_contract.replaced_response(idp_schema.IdentityProviderIconRead),
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity-providers:write"])],
    openapi_extra=core_middleware_body_limit.upload_limit(idp_constants.ICON_MAX_BYTES),
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def put_identity_provider_icon(
    idp_id: core_dependencies.UuidId,
    request: Request,
    file: UploadFile,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
    response: Response,
) -> idp_schema.IdentityProviderIconRead:
    """Set the icon an identity provider shows on the login page.

    Requires admin authentication with identity-providers:write scope. The icon replaces any custom icon URL
    until it is removed. Answers 201 when the provider had no uploaded icon and 200 when it replaced one.
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["identity-providers:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_identity_provider_icon(
    idp_id: core_dependencies.UuidId,
    request: Request,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> None:
    """Remove the uploaded icon of an identity provider.

    Requires admin authentication with identity-providers:write scope.
    """
    idp_icon_service.delete_icon(idp_id, storage, db)
