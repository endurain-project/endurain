import logging

from typing import Annotated, Callable

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from schemas import schema_users
from crud import crud_user_integrations, crud_users
from dependencies import (
    dependencies_database,
    dependencies_session,
    dependencies_global,
    dependencies_users,
)

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get("/users/number", response_model=int, tags=["users"])
async def read_users_number(
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    return crud_users.get_users_number(db)


@router.get(
    "/users/all/page_number/{page_number}/num_records/{num_records}",
    response_model=list[schema_users.User] | None,
    tags=["users"],
)
async def read_users_all_pagination(
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[
        Callable, Depends(dependencies_global.validate_pagination_values)
    ],
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the users from the database with pagination
    return crud_users.get_users_with_pagination(
        db=db, page_number=page_number, num_records=num_records
    )


@router.get(
    "/users/username/contains/{username}",
    response_model=list[schema_users.User] | None,
    tags=["users"],
)
async def read_users_contain_username(
    username: str,
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the users from the database by username
    return crud_users.get_user_if_contains_username(username=username, db=db)


@router.get(
    "/users/username/{username}",
    response_model=schema_users.User | None,
    tags=["users"],
)
async def read_users_username(
    username: str,
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the user from the database by username
    return crud_users.get_user_by_username(username=username, db=db)


@router.get("/users/id/{user_id}", response_model=schema_users.User, tags=["users"])
async def read_users_id(
    user_id: int,
    validate_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the users from the database by id
    return crud_users.get_user_by_id(user_id=user_id, db=db)


@router.get("/users/{username}/id", response_model=int, tags=["users"])
async def read_users_username_id(
    username: str,
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the users from the database by username
    return crud_users.get_user_id_by_username(username, db)


@router.get("/users/{user_id}/photo_path", response_model=str | None, tags=["users"])
async def read_users_id_photo_path(
    user_id: int,
    validate_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the photo_path from the database by id
    return crud_users.get_user_photo_path_by_id(user_id, db)


@router.get(
    "/users/{user_id}/photo_path_aux", response_model=str | None, tags=["users"]
)
async def read_users_id_photo_path_aux(
    user_id: int,
    validate_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Get the photo_path_aux from the database by id
    return crud_users.get_user_photo_path_aux_by_id(user_id, db)


@router.post("/users/create", response_model=int, status_code=201, tags=["users"])
async def create_user(
    user: schema_users.UserCreate,
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Create the user in the database
    created_user = crud_users.create_user(user, db)

    # Create the user integrations in the database
    crud_user_integrations.create_user_integrations(created_user.id, db)

    # Return the user id
    return created_user.id


@router.put("/users/edit", tags=["users"])
async def edit_user(
    user_attributtes: schema_users.User,
    validate_token_user_id: Annotated[
        Callable,
        Depends(
            dependencies_session.validate_token_and_if_user_id_equals_token_user_attributtes_id_if_not_validate_admin_access
        ),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Update the user in the database
    crud_users.edit_user(user_attributtes, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} updated successfully"}


@router.put("/users/edit/password", tags=["users"])
async def edit_user_password(
    user_attributtes: schema_users.UserEditPassword,
    validate_token_user_id: Annotated[
        Callable,
        Depends(
            dependencies_session.validate_token_and_if_user_id_equals_token_user_attributtes_password_id_if_not_validate_admin_access
        ),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Update the user password in the database
    crud_users.edit_user_password(user_attributtes.id, user_attributtes.password, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} password updated successfully"}


@router.put("/users/{user_id}/delete-photo", tags=["users"])
async def delete_user_photo(
    user_id: int,
    validate_token_user_id: Annotated[
        Callable,
        Depends(
            dependencies_session.validate_token_and_if_user_id_equals_token_user_id_if_not_validate_admin_access
        ),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Update the user photo_path in the database
    crud_users.delete_user_photo(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} photo deleted successfully"}


@router.delete("/users/{user_id}/delete", tags=["users"])
async def delete_user(
    user_id: int,
    validate_id: Annotated[Callable, Depends(dependencies_users.validate_user_id)],
    validate_token_validate_admin_access: Annotated[
        Callable, Depends(dependencies_session.validate_token_and_validate_admin_access)
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # Delete the user in the database
    crud_users.delete_user(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} deleted successfully"}
