"""User management router for authenticated operations."""

import os
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, UploadFile, Security, HTTPException, status
from sqlalchemy.orm import Session

import users.users.schema as users_schema
import users.users.crud as users_crud
import users.users.dependencies as users_dependencies
import users.users.utils as users_utils
import users.users.models as users_models

import users.users_identity_providers.crud as user_idp_crud

import sign_up_tokens.utils as sign_up_tokens_utils
import auth.security as auth_security
import auth.password_hasher as auth_password_hasher

import core.apprise as core_apprise
import core.database as core_database
import core.dependencies as core_dependencies
import core.file_uploads as core_file_uploads
import core.config as core_config

# Define the API router
router = APIRouter()


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    status_code=status.HTTP_200_OK,
    response_model=users_schema.UsersListResponse,
)
async def read_users_all_pagination(
    page_number: int,
    num_records: int,
    _validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> users_schema.UsersListResponse:
    """
    Retrieve paginated list of all users.

    Args:
        page_number: Page number to retrieve.
        num_records: Number of records per page.
        _validate_pagination_values: Pagination validation.
        _check_scopes: Authorization check.
        db: Database session dependency.

    Returns:
        Paginated list of users with total count.
    """
    total = users_crud.get_users_number(db)
    users = users_crud.get_users_with_pagination(db, page_number, num_records)

    # Enrich with IDP count before serializing
    enriched_users = []
    for user in users:
        idp_count = len(
            user_idp_crud.get_user_identity_providers_by_user_id(user.id, db)
        )
        user_read = users_schema.UsersRead.model_validate(user)
        user_read.external_auth_count = idp_count
        enriched_users.append(user_read)

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
async def read_users_contain_username(
    username: str,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> list[users_schema.UsersRead] | None:
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
async def read_users_username(
    username: str,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
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
async def read_users_email(
    email: str,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
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
async def read_users_id(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:read"])
    ],
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


@router.post(
    "", status_code=status.HTTP_201_CREATED, response_model=users_schema.UsersRead
)
async def create_user(
    user: users_schema.UsersCreate,
    _check_scope: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:write"])
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
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
        password_hasher: Password hasher dependency.
        db: Database session dependency.

    Returns:
        Created user data.
    """
    created_user = users_crud.create_user(user, password_hasher, db)

    # Create default data for the user
    users_utils.create_user_default_data(created_user.id, db)

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
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> str:
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
    return users_crud.get_user_by_id(user_id, db).photo_path


@router.put(
    "/{user_id}", status_code=status.HTTP_200_OK, response_model=users_schema.UsersRead
)
async def edit_user(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    user_attributtes: users_schema.UsersRead,
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
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
    db_user = await users_crud.edit_user(user_id, user_attributtes, db)

    # Enrich with IDP count before serializing
    idp_count = len(
        user_idp_crud.get_user_identity_providers_by_user_id(db_user.id, db)
    )
    user_read = users_schema.UsersRead.model_validate(db_user)
    user_read.external_auth_count = idp_count

    return user_read


@router.put(
    "/{user_id}/approve", status_code=status.HTTP_200_OK, response_model=dict[str, str]
)
async def approve_user(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:write"])
    ],
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
    users_crud.approve_user(user_id, db)

    # Send approval email
    await sign_up_tokens_utils.send_sign_up_approval_email(user_id, email_service, db)

    # Return success message
    return {"message": f"User ID {user_id} approved successfully."}


@router.put(
    "/{user_id}/password", status_code=status.HTTP_200_OK, response_model=dict[str, str]
)
async def edit_user_password(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    user_attributes: users_schema.UsersEditPassword,
    _check_scope: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:write"])
    ],
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> dict[str, str]:
    """
    Update user password.

    Args:
        user_id: ID of user to update password for.
        _validate_id: User ID validation dependency.
        user_attributes: New password data.
        _check_scope: Authorization check.
        password_hasher: Password hasher dependency.
        db: Database session dependency.

    Returns:
        Success message.
    """
    users_crud.edit_user_password(
        user_id, user_attributes.password, password_hasher, db
    )

    # Return success message
    return {"message": f"User ID {user_id} password updated successfully"}


@router.delete(
    "/{user_id}/photo", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_user_photo(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:write"])
    ],
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

    return None


@router.delete(
    "/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_user(
    user_id: int,
    _validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["users:write"])
    ],
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

    return None
