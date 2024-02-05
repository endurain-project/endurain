import logging

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from schemas import access_tokens as access_tokens_schema, users as users_schema
from crud import users as users_crud, user_integrations as user_integrations_crud
from dependencies import get_db

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.get("/users/number", response_model=int, tags=["users"])
async def read_users_number(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the number of users in the database"""
    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Get the number of users in the database
    return users_crud.get_users_number(db)


@router.get(
    "/users/all/page_number/{page_number}/num_records/{num_records}",
    response_model=list[users_schema.User],
    tags=["users"],
)
async def read_users_all_pagination(
    page_number: int,
    num_records: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the users from the database with pagination"""
    # Check if page_number higher than 0
    if not (int(page_number) > 0):
        # Raise an HTTPException with a 422 Unprocessable Entity status code
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Page Number",
        )

    # Check if num_records higher than 0
    if not (int(num_records) > 0):
        # Raise an HTTPException with a 422 Unprocessable Entity status code
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Number of Records",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Get the users from the database with pagination
    return users_crud.get_users_with_pagination(
        db=db, page_number=page_number, num_records=num_records
    )


@router.get(
    "/users/username/{username}", response_model=list[users_schema.User], tags=["users"]
)
async def read_users_username(
    username: str,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the users from the database by username"""
    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Get the users from the database by username
    return users_crud.get_user_by_username(username=username, db=db)


@router.get("/users/id/{user_id}", response_model=users_schema.User, tags=["users"])
async def read_users_id(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the users from the database by id"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        # Raise an HTTPException with a 422 Unprocessable Entity status code
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Get the users from the database by id
    return users_crud.get_user_by_id(user_id=user_id, db=db)


@router.get("/users/{username}/id", response_model=int, tags=["users"])
async def read_users_username_id(
    username: str,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the users from the database by username and return the user id"""
    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Get the users from the database by username
    return users_crud.get_user_id_by_username(username, db)


@router.get("/users/{user_id}/photo_path", response_model=str | None, tags=["users"])
async def read_users_id_photo_path(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the photo_path from the database by id"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Get the photo_path from the database by id
    return users_crud.get_user_photo_path_by_id(user_id, db)


@router.get(
    "/users/{user_id}/photo_path_aux", response_model=str | None, tags=["users"]
)
async def read_users_id_photo_path_aux(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Get the photo_path_aux from the database by id"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Get the photo_path_aux from the database by id
    return users_crud.get_user_photo_path_aux_by_id(user_id, db)


@router.post("/users/create", response_model=int, status_code=201, tags=["users"])
async def create_user(
    user: users_schema.UserCreate,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Create a new user in the database"""
    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Create the user in the database
    created_user = users_crud.create_user(user, db)

    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(created_user.id, db)

    # Return the user id
    return created_user.id


@router.put("/users/edit", tags=["users"])
async def edit_user(
    user_attributtes: users_schema.User,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Edit a user in the database"""
    # Check if user_id higher than 0
    if not (int(user_attributtes.id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Update the user in the database
    users_crud.edit_user(user_attributtes, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} updated successfully"}


@router.put("/users/edit/password", tags=["users"])
async def edit_user_password(
    user_attributtes: users_schema.UserEditPassword,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Edit a user password in the database"""
    # Check if user_id higher than 0
    if not (int(user_attributtes.id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if token id is different of user id. If yes checks if the token has admin access
    if user_attributtes.id != access_tokens_schema.get_token_user_id(token):
        # Check if the token has admin access
        access_tokens_schema.validate_token_admin_access(token)

    # Update the user password in the database
    users_crud.edit_user_password(user_attributtes.id, user_attributtes.password, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} password updated successfully"}


@router.put("/users/{user_id}/delete-photo", tags=["users"])
async def delete_user_photo(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    """Delete a user photo in the database"""
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if token id is different of user id. If yes checks if the token has admin access
    if user_id != access_tokens_schema.get_token_user_id(token):
        # Check if the token has admin access
        access_tokens_schema.validate_token_admin_access(token)

    # Update the user photo_path in the database
    users_crud.delete_user_photo(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} photo deleted successfully"}

@router.delete("/users/{user_id}/delete", tags=["users"])
async def delete_user(
    user_id: int,
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )
    
    # Validate the token expiration
    access_tokens_schema.validate_token_expiration(db, token)

    # Check if the token has admin access
    access_tokens_schema.validate_token_admin_access(token)

    # Delete the user in the database
    users_crud.delete_user(user_id, db)

    # Return success message
    return {"detail": f"User ID {user_id} deleted successfully"}