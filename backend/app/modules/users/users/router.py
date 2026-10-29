"""User management router for authenticated operations."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, UploadFile, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.account_security.integration_service as account_security_integration
import modules.auth.dependencies as auth_dependencies
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.users.users.deletion_job_service as users_deletion_job_service
import modules.users.users.dependencies as users_dependencies
import modules.users.users.photo_service as users_photo_service
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[users_schema.UsersRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read_all"])],
)
def read_users_all_pagination(
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    show_inactive: Annotated[
        bool | None,
        Query(description="Filter by inactive status"),
    ] = None,
    show_email_unverified: Annotated[
        bool | None,
        Query(description="Filter by email verification status"),
    ] = None,
    show_pending_approval: Annotated[
        bool | None,
        Query(description="Filter by pending approval status"),
    ] = None,
    show_external_auth: Annotated[
        bool | None,
        Query(description="Filter by external authentication status"),
    ] = None,
    show_local_auth: Annotated[
        bool | None,
        Query(description="Filter by local authentication status"),
    ] = None,
    username: Annotated[
        str | None,
        Query(description="Keep only users whose username contains this text"),
    ] = None,
) -> core_pagination.Page[users_schema.UsersRead]:
    """Retrieve paginated list of all users.

    Args:
        db: Database session dependency.
        page: The requested page and page size.
        show_inactive: Optional filter by inactive status.
        show_email_unverified: Optional filter by email verification status.
        show_pending_approval: Optional filter by pending approval status.
        show_external_auth: Optional filter by external authentication status.
        show_local_auth: Optional filter by local authentication status.
        username: Optional text the username must contain.

    Returns:
        Paginated list of users with total count.
    """
    return users_service.list_users(
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        show_inactive=show_inactive,
        show_email_unverified=show_email_unverified,
        show_pending_approval=show_pending_approval,
        show_external_auth=show_external_auth,
        show_local_auth=show_local_auth,
        username=username,
    )


@router.get(
    "/username/contains/{username}",
    response_model=users_schema.UserPublicPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read"])],
)
def read_users_contain_username(
    username: users_dependencies.Username,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> users_schema.UserPublicPage:
    """Search active users by partial username match, one page at a time.

    Args:
        username: Partial username to search for.
        page: The requested window of matches.
        db: Database session dependency.

    Returns:
        The page of matching users' public projections.
    """
    return users_service.search_public_users(username, page, db)


@router.get(
    "/username/{username}",
    response_model=users_schema.UsersRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read_all"])],
)
def read_users_username(
    username: users_dependencies.Username,
    db: core_dependencies.DbSession,
    response: Response,
) -> users_schema.UsersRead:
    """Get user by exact username.

    Args:
        username: Exact username to search for.
        db: Database session dependency.
        response: The response, which carries the user's ETag.

    Returns:
        The user.

    Raises:
        NotFoundError: If there is no such user.
    """
    user = users_service.require_user_by_username(username, db)
    core_etag.set_etag(response, user.version)
    return user


@router.post(
    "/email/lookup",
    response_model=users_schema.UsersRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read_all"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def lookup_user_by_email(
    request: Request,
    lookup: users_schema.UsersEmailLookup,
    db: core_dependencies.DbSession,
    response: Response,
) -> users_schema.UsersRead:
    """Get a user by email address.

    The address travels in the request body, so it never reaches access logs or proxy caches
    through the URL.

    Args:
        request: The incoming request, read by the rate limiter.
        lookup: The email address to search for.
        db: Database session dependency.
        response: The response, which carries the user's ETag.

    Returns:
        The user.

    Raises:
        NotFoundError: If there is no such user.
    """
    user = users_service.require_user_by_email(lookup.email, db)
    core_etag.set_etag(response, user.version)
    return user


@router.get(
    "/id/{user_id}",
    response_model=users_schema.UserPublicRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read"])],
)
def read_users_id(
    user_id: core_dependencies.PositiveId,
    db: core_dependencies.DbSession,
) -> users_schema.UserPublicRead:
    """Get a user's public projection by ID.

    Args:
        user_id: User ID to retrieve.
        db: Database session dependency.

    Returns:
        The public projection.

    Raises:
        NotFoundError: If the user does not exist.
    """
    return users_service.get_public_profile(user_id, db)


@router.get(
    "/{user_id}",
    response_model=users_schema.UsersRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read_all"])],
)
def read_users_full(
    user_id: core_dependencies.PositiveId,
    db: core_dependencies.DbSession,
    response: Response,
) -> users_schema.UsersRead:
    """Get a user's full record by ID (admin operation).

    Args:
        user_id: User ID to retrieve.
        db: Database session dependency.
        response: The response, which carries the user's ETag.

    Returns:
        The full record.

    Raises:
        NotFoundError: If the user does not exist.
    """
    user = users_service.require_user(user_id, db)
    core_etag.set_etag(response, user.version)
    return user


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=users_schema.UsersRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def create_user(
    request: Request,
    user: users_schema.UsersCreate,
    db: core_dependencies.DbSession,
) -> users_schema.UsersRead:
    """Create a new user (admin operation).

    Args:
        request: The incoming request, read by the rate limiter.
        user: User creation data.
        db: Database session dependency.

    Returns:
        Created user data.
    """
    return users_service.create_user(user, db)


@router.post(
    "/{user_id}/photo",
    status_code=status.HTTP_201_CREATED,
    response_model=users_schema.UserPhotoRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def upload_user_image(
    request: Request,
    user_id: core_dependencies.PositiveId,
    file: UploadFile,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> users_schema.UserPhotoRead:
    """Upload user profile image.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to upload image for.
        file: Uploaded image file.
        storage: The platform storage provider.
        db: Database session dependency.

    Returns:
        The servable URL of the new photo.
    """
    users_photo_service.upload_photo(user_id, file, storage, db)
    return users_schema.UserPhotoRead(photo_path=users_service.require_user(user_id, db).photo_path)


@router.put(
    "/{user_id}",
    response_model=users_schema.UsersRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    user_attributtes: users_schema.UsersEdit,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> users_schema.UsersRead:
    """Update user information.

    A change of email, access type or active flag signs the edited user out everywhere.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to update.
        user_attributtes: User data to update.
        token_user_id: ID of the administrator making the edit.
        db: Database session dependency.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        Updated user data.
    """
    updated = users_service.edit_user(user_id, user_attributtes, token_user_id, db, if_match=if_match)
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
    user_attributes: users_schema.UsersAdminEditPassword,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Update another user's password.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to update password for.
        user_attributes: New password data.
        token_user_id: ID of the administrator making the change.
        db: Database session dependency.
    """
    users_service.change_user_password(user_id, user_attributes.password, token_user_id, db)


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
    users_photo_service.delete_photo(user_id, storage, db)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=users_schema.UserDeletionStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def delete_user(
    request: Request,
    user_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    states: users_dependencies.UserDeletionStateStoreDep,
    storage: core_dependencies.Storage,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> users_schema.UserDeletionStatus:
    """Queue the deletion of another user's account.

    The user is signed out and deactivated at once and a background job erases their data. Poll
    ``GET /users/{user_id}/deletion`` for the outcome; a failed deletion is requested again.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of user to delete.
        token_user_id: ID of the administrator making the request.
        states: Shared store of the deletion's state.
        storage: The platform storage provider.
        if_match: The ``If-Match`` precondition.
        db: Database session dependency.

    Returns:
        The deletion's initial status.

    Raises:
        PermissionDeniedError: If the administrator targets their own account.
        NotFoundError: If the user does not exist.
        PreconditionFailedError: If the user changed since the client read it.
        ConflictError: If the user is the only administrator, or a deletion is already pending.
    """
    return users_deletion_job_service.request_deletion_by_administrator(
        user_id, token_user_id, states, storage, db, if_match=if_match
    )


@router.get(
    "/{user_id}/deletion",
    response_model=users_schema.UserDeletionStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read_all"])],
)
def read_user_deletion_status(
    user_id: core_dependencies.PositiveId,
    states: users_dependencies.UserDeletionStateStoreDep,
) -> users_schema.UserDeletionStatus:
    """Report where a user's account deletion is.

    Args:
        user_id: ID of the user being deleted.
        states: Shared store of the deletion's state.

    Returns:
        The deletion's status.

    Raises:
        NotFoundError: If no deletion is recorded or it has expired.
    """
    return users_deletion_job_service.get_deletion_status(user_id, states)


@router.get(
    "/{user_id}/identity-providers",
    response_model=list[auth_identity_links_schema.IdentityProviderLinkRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:read_all"])],
)
def get_user_identity_providers(
    user_id: core_dependencies.PositiveId,
    db: core_dependencies.DbSession,
) -> list[auth_identity_links_schema.IdentityProviderLinkRead]:
    """List the identity provider links of a specific user (admin).

    Args:
        user_id: ID of the user whose identity provider links to retrieve.
        db: Database session.

    Returns:
        The user's enriched identity provider links (empty list if none).
    """
    return account_security_integration.get_user_identity_provider_links(user_id, db)


@router.delete(
    "/{user_id}/identity-providers/{idp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["users:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_user_identity_provider(
    request: Request,
    user_id: core_dependencies.PositiveId,
    idp_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Unlink an identity provider from another user (admin).

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: ID of the user to unlink the identity provider from.
        idp_id: ID of the identity provider to unlink.
        token_user_id: ID of the administrator making the change.
        db: Database session.

    Returns:
        None
    """
    users_service.unlink_identity_provider(user_id, idp_id, token_user_id, db)
