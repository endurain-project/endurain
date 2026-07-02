"""User management router for authenticated operations."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

import auth.dependencies as auth_dependencies
import auth.identity_providers.links.schema as auth_identity_links_schema
import auth.identity_service as auth_identity_service
import auth.sign_up_tokens.utils as sign_up_tokens_utils
import core.apprise as core_apprise
import core.database as core_database
import core.dependencies as core_dependencies
import users.users.crud as users_crud
import users.users.dependencies as users_dependencies
import users.users.schema as users_schema
import users.users.utils as users_utils

# Define the API router
router = APIRouter()


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UsersListResponse,
)
def read_users_all_pagination(
    _validate_pagination_values_on_query: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values_on_query)
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    page_number: Annotated[
        int | None,
        Query(ge=1, description="Pagination page number"),
    ] = None,
    num_records: Annotated[
        int | None,
        Query(
            ge=1,
            description="Number of records per page",
        ),
    ] = None,
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
) -> users_schema.UsersListResponse:
    """
    Retrieve paginated list of all users.

    Args:
        _validate_pagination_values: Pagination validation.
        _check_scopes: Authorization check.
        db: Database session dependency.
        page_number: Optional page number to retrieve.
        num_records: Optional number of records per page.
        show_inactive: Optional filter by inactive status.
        show_email_unverified: Optional filter by email verification status.
        show_pending_approval: Optional filter by pending approval status.
        show_external_auth: Optional filter by external authentication status.
        show_local_auth: Optional filter by local authentication status.

    Returns:
        Paginated list of users with total count.
    """
    total: int = users_crud.get_users_number(
        db,
        show_inactive,
        show_email_unverified,
        show_pending_approval,
    )
    users: list[users_schema.UsersRead] = users_crud.get_users_with_pagination(
        db,
        page_number,
        num_records,
        show_inactive,
        show_email_unverified,
        show_pending_approval,
    )

    # Batch fetch IdP link counts for all users in a single grouped query
    user_ids: list[int] = [user.id for user in users]
    idp_counts: dict[int, int] = identity_service.get_identity_link_counts_for_users(user_ids)

    # Enrich with IDP count before serializing
    enriched_users: list[users_schema.UsersRead] = []
    for user in users:
        idp_count: int = idp_counts.get(user.id, 0)
        user.external_auth_count = idp_count

        # Apply external/local auth filters
        if idp_count > 0 and show_external_auth is False:
            continue
        if idp_count == 0 and show_local_auth is False:
            continue

        enriched_users.append(user)

    return users_schema.UsersListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=enriched_users,
    )


@router.get(
    "/username/contains/{username}",
    status_code=status.HTTP_200_OK,
    response_model=list[users_schema.UsersRead] | None,
)
def read_users_contain_username(
    username: str,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> list[users_schema.UsersRead] | users_schema.UsersRead | None:
    """
    Search users by partial username match.

    Args:
        username: Partial username to search for.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        List of users matching the search.
    """
    return users_crud.get_user_by_username(username=username, db=db, contains=True)


@router.get(
    "/username/{username}",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UsersRead | None,
)
def read_users_username(
    username: str,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UsersRead | None:
    """
    Get user by exact username.

    Args:
        username: Exact username to search for.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        User if found, None otherwise.
    """
    return users_crud.get_user_by_username(username, db)


@router.get(
    "/email/{email}",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UsersRead | None,
)
def read_users_email(
    email: str,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UsersRead | None:
    """
    Get user by email address.

    Args:
        email: Email address to search for.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        User if found, None otherwise.
    """
    return users_crud.get_user_by_email(email, db)


@router.get(
    "/id/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UsersRead | None,
)
def read_users_id(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UsersRead | None:
    """
    Get user by ID.

    Args:
        user_id: User ID to retrieve.
        _validate_id: User ID validation dependency.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        User if found, None otherwise.
    """
    return users_crud.get_user_by_id(user_id, db)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=users_schema.UsersRead)
def create_user(
    user: users_schema.UsersCreate,
    _check_scope: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UsersRead:
    """
    Create a new user (admin operation).

    Args:
        user: User creation data.
        _check_scope: Authorization check.
        identity_service: Identity service dependency.
        db: Database session dependency.

    Returns:
        Created user data.
    """
    created_user: users_schema.UsersRead = users_crud.create_user(user, identity_service, db)

    # Create default data for the user
    users_utils.create_user_default_data(created_user.id, identity_service, db)

    # Return the created user
    return created_user


@router.post(
    "/{user_id}/image",
    status_code=status.HTTP_201_CREATED,
    response_model=str,
)
async def upload_user_image(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    file: UploadFile,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> str | None:
    """
    Upload user profile image.

    Args:
        user_id: ID of user to upload image for.
        _validate_id: User ID validation dependency.
        file: Uploaded image file.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        Path to uploaded image.
    """
    await users_utils.save_user_image_file(user_id, file, db)
    # Fetch the persisted user off the event loop (blocking sync DB read).
    user: users_schema.UsersRead | None = await run_in_threadpool(users_crud.get_user_by_id, user_id, db)
    return user.photo_path if user and user.photo_path else None


@router.put("/{user_id}", status_code=status.HTTP_200_OK, response_model=users_schema.UsersRead)
async def edit_user(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    user_attributtes: users_schema.UsersRead,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> users_schema.UsersRead:
    """
    Update user information.

    Args:
        user_id: ID of user to update.
        _validate_id: User ID validation dependency.
        user_attributtes: User data to update.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        Updated user data.
    """
    db_user: users_schema.UsersRead = await users_crud.edit_user(user_id, user_attributtes, db)

    # Enrich with IDP count before serializing. The lookup is a blocking
    # sync DB call, so offload it to a worker thread to keep the event
    # loop responsive.
    idp_counts: dict[int, int] = await run_in_threadpool(
        identity_service.get_identity_link_counts_for_users, [db_user.id]
    )
    idp_count: int = idp_counts.get(db_user.id, 0)
    db_user.external_auth_count = idp_count

    return db_user


@router.put("/{user_id}/approve", status_code=status.HTTP_200_OK, response_model=dict[str, str])
async def approve_user(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    email_service: Annotated[
        core_apprise.AppriseService,
        Depends(core_apprise.get_email_service),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> dict[str, str]:
    """
    Approve pending user account.

    Args:
        user_id: ID of user to approve.
        _validate_id: User ID validation dependency.
        _check_scopes: Authorization check.
        email_service: Email service dependency.
        db: Database session dependency.

    Returns:
        Success message.
    """
    # Approve the user off the event loop (blocking sync DB write).
    await run_in_threadpool(users_crud.approve_user, user_id, db)

    # Send approval email
    await sign_up_tokens_utils.send_sign_up_approval_email(user_id, email_service, db)

    # Return success message
    return {"message": f"User ID {user_id} approved successfully."}


@router.put("/{user_id}/password", status_code=status.HTTP_200_OK, response_model=dict[str, str])
def edit_user_password(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    user_attributes: users_schema.UsersAdminEditPassword,
    _check_scope: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> dict[str, str]:
    """
    Update user password.

    Args:
        user_id: ID of user to update password for.
        _validate_id: User ID validation dependency.
        user_attributes: New password data.
        _check_scope: Authorization check.
        identity_service: Identity service dependency.

    Returns:
        Success message.
    """
    identity_service.change_managed_user_password(
        user_id,
        user_attributes.password,
    )

    # Return success message
    return {"message": f"User ID {user_id} password updated successfully"}


@router.delete("/{user_id}/photo", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_user_photo(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Delete user profile photo.

    Args:
        user_id: ID of user whose photo to delete.
        _validate_id: User ID validation dependency.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        None
    """
    await users_crud.update_user_photo(user_id, db)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_user(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """
    Delete user account.

    Args:
        user_id: ID of user to delete.
        _validate_id: User ID validation dependency.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        None
    """
    await users_crud.delete_user(user_id, db)


@router.get(
    "/{user_id}/identity-providers",
    status_code=status.HTTP_200_OK,
    response_model=list[auth_identity_links_schema.UsersIdentityProviderResponse],
)
def get_user_identity_providers(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:read"])],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> list[auth_identity_links_schema.UsersIdentityProviderResponse]:
    """
    List the identity provider links of a specific user (admin).

    Args:
        user_id: ID of the user whose identity provider links to retrieve.
        _validate_id: User ID validation dependency.
        _check_scopes: Authorization check (users:read scope).
        identity_service: Identity service dependency.

    Returns:
        The user's enriched identity provider links (empty list if none).
    """
    return identity_service.get_user_identity_provider_links(user_id)


@router.delete(
    "/{user_id}/identity-providers/{idp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_user_identity_provider(
    user_id: int,
    idp_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["users:write"])],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
) -> None:
    """
    Unlink an identity provider from a specific user (admin).

    Args:
        user_id: ID of the user to unlink the identity provider from.
        idp_id: ID of the identity provider to unlink.
        _validate_id: User ID validation dependency.
        _check_scopes: Authorization check (users:write scope).
        identity_service: Identity service dependency.

    Returns:
        None
    """
    identity_service.admin_delete_identity_provider_link(user_id, idp_id)
