from typing import Annotated, Callable

from fastapi import APIRouter, Depends, UploadFile, Security, HTTPException, status
from sqlalchemy.orm import Session

import users.schema as users_schema
import users.crud as users_crud
import users.dependencies as users_dependencies
import users.utils as users_utils

import user_integrations.crud as user_integrations_crud

import user_default_gear.crud as user_default_gear_crud

import health_targets.crud as health_targets_crud

import session.security as session_security

import core.database as core_database
import core.dependencies as core_dependencies

# Define the API router
router = APIRouter()


@router.get("/number", response_model=int)
async def read_users_number(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    return users_crud.get_users_number(db)


@router.get(
    "/page_number/{page_number}/num_records/{num_records}",
    response_model=list[users_schema.User] | None,
)
async def read_users_all_pagination(
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(core_dependencies.validate_pagination_values)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the users from the database with pagination
    return users_crud.get_users_with_pagination(db, page_number, num_records)


@router.get(
    "/username/contains/{username}",
    response_model=list[users_schema.User] | None,
)
async def read_users_contain_username(
    username: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the users from the database by username
    return users_crud.get_user_if_contains_username(username=username, db=db)


@router.get(
    "/username/{username}",
    response_model=users_schema.User | None,
)
async def read_users_username(
    username: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the user from the database by username
    return users_crud.get_user_by_username(username, db)


@router.get(
    "/email/{email}",
    response_model=users_schema.User | None,
)
async def read_users_email(
    email: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the users from the database by email
    return users_crud.get_user_by_email(email, db)


@router.get("/id/{user_id}", response_model=users_schema.User)
async def read_users_id(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the users from the database by id
    return users_crud.get_user_by_id(user_id, db)


@router.post("", response_model=users_schema.User, status_code=201)
async def create_user(
    user: users_schema.UserCreate,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Create the user in the database
    created_user = users_crud.create_user(user, db)

    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(created_user.id, db)

    # Create the user health targets
    health_targets_crud.create_health_targets(created_user.id, db)

    # Create the user default gear
    user_default_gear_crud.create_user_default_gear(created_user.id, db)

    # Return the user with formatted birthdate
    return users_utils.format_user_birthdate(created_user)


@router.post(
    "/{user_id}/image",
    status_code=201,
    response_model=str | None,
)
async def upload_user_image(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    file: UploadFile,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    return await users_utils.save_user_image(user_id, file, db)


@router.put("/{user_id}")
async def edit_user(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    user_attributtes: users_schema.User,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the user in the database
    users_crud.edit_user(user_id, user_attributtes, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} updated successfully"}


@router.put("/{user_id}/password")
async def edit_user_password(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    user_attributes: users_schema.UserEditPassword,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Check if the password meets the complexity requirements
    is_valid, message = session_security.is_password_complexity_valid(
        user_attributes.password
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Update the user password in the database
    users_crud.edit_user_password(user_id, user_attributes.password, db)

    # Return success message
    return {f"User ID {user_id} password updated successfully"}


@router.delete("/{user_id}/photo")
async def delete_user_photo(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the user photo_path in the database
    users_crud.delete_user_photo(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} photo deleted successfully"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Delete the user in the database
    users_crud.delete_user(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} deleted successfully"}
