"""User management router for authenticated operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, Security, UploadFile, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.file_uploads as core_file_uploads
import core.location as core_location
import core.middleware_body_limit as core_middleware_body_limit
import core.openapi_contract as core_openapi_contract
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.auth.schema as auth_schema
import modules.users.users.constants as users_constants
import modules.users.users.deletion_job_service as users_deletion_job_service
import modules.users.users.dependencies as users_dependencies
import modules.users.users.photo_service as users_photo_service
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[users_schema.UserRead] | users_schema.UserPublicPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read"])],
)
def read_users(
    db: core_dependencies.DbSession,
    scopes: auth_dependencies.CurrentScopes,
    page: users_dependencies.DirectoryPage,
    active: Annotated[
        bool | None,
        Query(description="Keep only active (true) or inactive (false) users; needs `users:read-all`"),
    ] = None,
    email_verified: Annotated[
        bool | None,
        Query(description="Keep only users whose email is verified (true) or not (false); needs `users:read-all`"),
    ] = None,
    pending_approval: Annotated[
        bool | None,
        Query(description="Keep only users awaiting admin approval (true) or not (false); needs `users:read-all`"),
    ] = None,
    external_auth: Annotated[
        bool | None,
        Query(
            description="Keep only users with (true) or without (false) a linked identity provider; needs `users:read-all`"
        ),
    ] = None,
    username: Annotated[
        str | None,
        Query(min_length=1, max_length=250, description="Keep only the user with this exact username"),
    ] = None,
    username_contains: Annotated[
        str | None,
        Query(
            min_length=users_dependencies.MIN_SEARCH_TERM_LENGTH,
            max_length=250,
            description="Keep only users whose username contains this text (at least 3 characters)",
        ),
    ] = None,
) -> core_pagination.Page[users_schema.UserRead] | users_schema.UserPublicPage:
    """List users, one page at a time.

    With `users:read-all` the page holds full records and every filter is available. With only `users:read` it
    holds public projections of active users who are discoverable (those who switched off "Let others find me
    in search" are left out; their profile stays reachable by id), a state filter is refused with 403, and a request
    without `username` or `username_contains` of at least 3 characters is refused with 422.
    `num_records` defaults to the server's page size and may not exceed it; a larger value is refused with 422.
    """
    if "users:read-all" in scopes:
        return users_service.list_users(
            db,
            page_number=page.page_number,
            num_records=page.num_records,
            active=active,
            email_verified=email_verified,
            pending_approval=pending_approval,
            external_auth=external_auth,
            username=username,
            username_contains=username_contains,
        )
    if any(state is not None for state in (active, email_verified, pending_approval, external_auth)):
        auth_dependencies.require_scopes(scopes, "users:read-all")
    users_dependencies.require_search_term(username, username_contains)
    return users_service.list_public_users(page, db, username=username, username_contains=username_contains)


@router.get(
    "/{user_id}",
    response_model=users_schema.UserRead | users_schema.UserPublicRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read"])],
)
def read_user(
    user_id: core_dependencies.PositiveId,
    db: core_dependencies.DbSession,
    scopes: auth_dependencies.CurrentScopes,
    response: Response,
) -> users_schema.UserRead | users_schema.UserPublicRead:
    """Get a user by ID.

    With `users:read-all` the answer is the full record, with its `ETag`. With only `users:read` it is the
    public projection, and a user who is inactive or awaits approval is 404.
    """
    if "users:read-all" in scopes:
        user = users_service.require_user_with_pending_email(user_id, db)
        core_etag.set_etag(response, user.version)
        return user
    return users_service.get_public_profile(user_id, db)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=users_schema.UserRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def create_user(
    request: Request,
    user: users_schema.UserAdminCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
    response: Response,
) -> users_schema.UserRead:
    """Create a new user (admin operation).

    An administrator account needs the creating administrator's own step-up verification in `step_up` (their
    current password or, for an account without one, a fresh identity-provider sign-in, and an MFA code when MFA
    is enabled). A regular account needs no `step_up`.

    The `password` is optional when the server has mail configured: without it the account is created active with
    no password and its owner is emailed a link, valid for 24 hours, to choose one. Without mail, or for an inactive
    account, a missing password is refused.

    Args:
        request: The incoming request, read by the rate limiter.
        user: User creation data, and the administrator's step-up.
        token_user_id: ID of the administrator creating the user.
        token_session_id: Session ID of the administrator.
        step_up_store: Step-up lockout store.
        db: Database session dependency.
        response: The response, whose ``Location`` names where the user is read.

    Returns:
        Created user data.
    """
    created = users_service.create_user(
        user.to_create(), user.step_up, token_user_id, token_session_id, step_up_store, db
    )
    core_location.set_location(response, request, "read_user", user_id=created.id)
    core_etag.set_etag(response, created.version)
    return created


@router.put(
    "/{user_id}/photo",
    status_code=status.HTTP_201_CREATED,
    response_model=users_schema.UserPhotoRead,
    responses=core_openapi_contract.replaced_response(users_schema.UserPhotoRead),
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    openapi_extra=core_middleware_body_limit.upload_limit(
        core_file_uploads.max_bytes_for(core_file_uploads.UploadKind.IMAGE)
    ),
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def put_user_image(
    request: Request,
    user_id: core_dependencies.PositiveId,
    file: UploadFile,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
    response: Response,
) -> users_schema.UserPhotoRead:
    """Set a user's profile image.

    Answers 201 when the user had no photo and 200 when it replaced one.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to upload image for.
        file: Uploaded image file.
        storage: The platform storage provider.
        db: Database session dependency.
        response: The response, whose status is 200 when a photo was replaced.

    Returns:
        The servable URL of the new photo.
    """
    replaced = users_photo_service.upload_photo(user_id, file, storage, db, audit=True)
    if replaced:
        response.status_code = status.HTTP_200_OK
    return users_schema.UserPhotoRead(photo_path=users_service.require_user(user_id, db).photo_path)


@router.patch(
    "/{user_id}",
    response_model=users_schema.UserRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    user_attributtes: users_schema.UserAdminEdit,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> users_schema.UserRead:
    """Update user information.

    A change of email, access type or active flag needs the administrator's own step-up verification in
    `step_up` (their current password or, for an account without one, a fresh identity-provider sign-in,
    and an MFA code when MFA is enabled), and signs the edited user out everywhere. An edit that changes none
    of the three needs no `step_up`.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to update.
        user_attributtes: User data to update, and the administrator's step-up.
        token_user_id: ID of the administrator making the edit.
        token_session_id: Session ID of the administrator.
        step_up_store: Step-up lockout store.
        db: Database session dependency.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        Updated user data.
    """
    updated = users_service.edit_user(
        user_id,
        user_attributtes.to_edit(),
        user_attributtes.step_up,
        token_user_id,
        token_session_id,
        step_up_store,
        db,
        if_match=if_match,
    )
    core_etag.set_etag(response, updated.version)
    return updated


@router.post(
    "/{user_id}/approve",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def approve_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    db: core_dependencies.DbSession,
) -> None:
    """Approve pending user account.

    A user who is not awaiting approval, is deactivated or is queued for deletion, or whose email is not verified
    while sign-up requires verification, is refused with 409.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to approve.
        db: Database session dependency.
    """
    users_service.approve_user(user_id, db)


@router.post(
    "/{user_id}/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def edit_user_password(
    request: Request,
    user_id: core_dependencies.PositiveId,
    user_attributes: users_schema.UserAdminEditPassword,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Update another user's password.

    Requires the administrator's own step-up verification: their current password (or, for an account
    without one, a fresh identity-provider sign-in), and an MFA code when MFA is enabled.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to update password for.
        user_attributes: New password data and the administrator's step-up.
        token_user_id: ID of the administrator making the change.
        token_session_id: Session ID of the administrator.
        step_up_store: Step-up lockout store.
        db: Database session dependency.

    Raises:
        HTTPException: 422 if the password is too short, too common or matches the account's details.
    """
    users_service.change_user_password(user_id, user_attributes, token_user_id, token_session_id, step_up_store, db)


@router.post(
    "/{user_id}/mfa/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def reset_user_mfa(
    request: Request,
    user_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Reset another user's two-factor authentication.

    Requires the administrator's own step-up verification: their current password (or, for an account
    without one, a fresh identity-provider sign-in), and an MFA code when MFA is enabled. The user's MFA
    secret and backup codes are removed, all of their sessions end and they are notified. A user without MFA is
    refused with 409.
    """
    users_service.reset_user_mfa(user_id, body, token_user_id, token_session_id, step_up_store, db)


@router.post(
    "/{user_id}/password/require-change",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def require_user_password_change(
    request: Request,
    user_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Require another user to choose a new password at their next sign-in.

    Requires the administrator's own step-up verification: their current password (or, for an account
    without one, a fresh identity-provider sign-in), and an MFA code when MFA is enabled. The user keeps their
    current password until then, all of their sessions end and they are notified. A user without a local
    password is refused with 409; single sign-on sign-ins are unaffected.
    """
    users_service.require_user_password_change(user_id, body, token_user_id, token_session_id, step_up_store, db)


@router.delete(
    "/{user_id}/photo",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_user_photo(
    request: Request,
    user_id: core_dependencies.PositiveId,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> None:
    """Delete user profile photo.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user whose photo to delete.
        storage: The platform storage provider.
        db: Database session dependency.

    Returns:
        None
    """
    users_photo_service.delete_photo(user_id, storage, db, audit=True)


@router.post(
    "/{user_id}/delete",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=users_schema.UserDeletionStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def delete_user(
    request: Request,
    response: Response,
    user_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    states: users_dependencies.UserDeletionStateStoreDep,
    storage: core_dependencies.Storage,
    mail: core_dependencies.Mail,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> users_schema.UserDeletionStatus:
    """Queue the deletion of another user's account.

    Requires the administrator's own step-up verification: their current password (or, for an account
    without one, a fresh identity-provider sign-in), and an MFA code when MFA is enabled. The user is signed
    out and deactivated at once and a background job erases their data. Poll ``GET /jobs/{job_id}`` for the
    outcome; a failed deletion is requested again.

    Args:
        request: The incoming request, read by the rate limiter.
        response: The response, which names the job and when to poll it.
        user_id: ID of user to delete.
        body: The administrator's step-up verification.
        token_user_id: ID of the administrator making the request.
        token_session_id: Session ID of the administrator.
        step_up_store: Step-up lockout store.
        states: Shared store of the deletion's state.
        storage: The platform storage provider.
        mail: The platform mail provider.
        if_match: The ``If-Match`` precondition.
        db: Database session dependency.

    Returns:
        The deletion's initial status, with the id of the job that reads it.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        NotFoundError: If the user does not exist.
        PreconditionFailedError: If the user changed since the client read it.
        LastAdministratorError: If the user is the only administrator.
        JobAlreadyRunningError: If a deletion is already pending.
    """
    deletion = users_deletion_job_service.request_deletion_by_administrator(
        user_id,
        token_user_id,
        token_session_id,
        body.step_up,
        step_up_store,
        states,
        storage,
        mail,
        db,
        if_match=if_match,
    )
    core_location.set_job_location(response, request, deletion.id, users_constants.DELETION_POLL_SECONDS)
    return deletion


@router.get(
    "/{user_id}/identity-providers",
    response_model=auth_identity_links_schema.IdentityProviderLinkPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read-all"])],
)
def get_user_identity_providers(
    user_id: core_dependencies.PositiveId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> auth_identity_links_schema.IdentityProviderLinkPage:
    """List one page of a specific user's identity provider links (admin).

    Args:
        user_id: ID of the user whose identity provider links to retrieve.
        page: The requested window.
        db: Database session.

    Returns:
        The page of the user's enriched identity provider links, oldest first.
    """
    return account_security_integration.get_user_identity_provider_links(user_id, page, db)


@router.post(
    "/{user_id}/identity-providers/{idp_id}/unlink",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_user_identity_provider(
    request: Request,
    user_id: core_dependencies.PositiveId,
    idp_id: core_dependencies.PositiveId,
    body: auth_schema.StepUpRequest,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Unlink an identity provider from another user (admin).

    Requires the administrator's own step-up verification: their current password (or, for an account
    without one, a fresh identity-provider sign-in), and an MFA code when MFA is enabled.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of the user to unlink the identity provider from.
        idp_id: ID of the identity provider to unlink.
        body: The administrator's step-up verification.
        token_user_id: ID of the administrator making the change.
        token_session_id: Session ID of the administrator.
        step_up_store: Step-up lockout store.
        db: Database session.

    Returns:
        None
    """
    users_service.unlink_identity_provider(
        user_id, idp_id, token_user_id, token_session_id, body.step_up, step_up_store, db
    )
