import os
import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, Security
from sqlalchemy.orm import Session

import shutil

import users.schema as users_schema
import users.crud as users_crud
import users.dependencies as users_dependencies

import user_integrations.crud as user_integrations_crud

import session.security as session_security

import database
import dependencies_global

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get("/me", response_model=users_schema.UserMe)
async def read_users_me(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["profile"])
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the user from the database
    user = users_crud.get_user_by_id(token_user_id, db)

    # If the user does not exist raise the exception
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials (user not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user.id, db
    )

    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials (user integrations not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.is_strava_linked = 1 if user_integrations.strava_token else 0

    # Return the user
    return user


@router.get("/number", response_model=int)
async def read_users_number(
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    return users_crud.get_users_number(db)


@router.get(
    "/all/page_number/{page_number}/num_records/{num_records}",
    response_model=list[users_schema.User] | None,
    tags=["users"],
)
async def read_users_all_pagination(
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(dependencies_global.validate_pagination_values)
    ],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the users from the database with pagination
    return users_crud.get_users_with_pagination(
        db=db, page_number=page_number, num_records=num_records
    )


@router.get(
    "/username/contains/{username}",
    response_model=list[users_schema.User] | None,
    tags=["users"],
)
async def read_users_contain_username(
    username: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the users from the database by username
    return users_crud.get_user_if_contains_username(username=username, db=db)


@router.get(
    "/username/{username}",
    response_model=users_schema.User | None,
    tags=["users"],
)
async def read_users_username(
    username: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the user from the database by username
    return users_crud.get_user_by_username(username=username, db=db)


@router.get("/id/{user_id}", response_model=users_schema.User)
async def read_users_id(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the users from the database by id
    return users_crud.get_user_by_id(user_id=user_id, db=db)


@router.get("/{username}/id", response_model=int)
async def read_users_username_id(
    username: str,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the users from the database by username
    return users_crud.get_user_id_by_username(username, db)


@router.get("/{user_id}/photo_path", response_model=str | None)
async def read_users_id_photo_path(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:read"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Get the photo_path from the database by id
    return users_crud.get_user_photo_path_by_id(user_id, db)


@router.post("/create", response_model=int, status_code=201)
async def create_user(
    user: users_schema.UserCreate,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Create the user in the database
    created_user = users_crud.create_user(user, db)

    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(created_user.id, db)

    # Return the user id
    return created_user.id


@router.post(
    "/{user_id}/upload/image",
    status_code=201,
    response_model=str | None,
    tags=["users"],
)
async def upload_user_image(
    user_id: int,
    token_user_id: Annotated[
        Callable,
        Depends(
            session_security.get_token_user_id
        ),
    ],
    file: UploadFile,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    try:
        upload_dir = "user_images"
        os.makedirs(upload_dir, exist_ok=True)

        # Get file extension
        _, file_extension = os.path.splitext(file.filename)
        filename = f"{user_id}{file_extension}"

        file_path_to_save = os.path.join(upload_dir, filename)

        with open(file_path_to_save, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return users_crud.edit_user_photo_path(user_id, file_path_to_save, db)
    except Exception as err:
        # Log the exception
        logger.error(f"Error in upload_user_image: {err}", exc_info=True)

        # Remove the file after processing
        if os.path.exists(file_path_to_save):
            os.remove(file_path_to_save)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.put("/edit")
async def edit_user(
    user_attributtes: users_schema.User,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Update the user in the database
    users_crud.edit_user(user_attributtes, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} updated successfully"}


@router.put("/edit/password")
async def edit_user_password(
    user_attributtes: users_schema.UserEditPassword,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Update the user password in the database
    users_crud.edit_user_password(user_attributtes.id, user_attributtes.password, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} password updated successfully"}


@router.put("/{user_id}/delete-photo")
async def delete_user_photo(
    user_id: int,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Update the user photo_path in the database
    users_crud.delete_user_photo(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} photo deleted successfully"}


@router.delete("/{user_id}/delete")
async def delete_user(
    user_id: int,
    validate_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["users:write"])
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # Delete the user in the database
    users_crud.delete_user(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} deleted successfully"}
