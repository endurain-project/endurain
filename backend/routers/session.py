import logging

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from crud import users as users_crud, user_integrations as user_integrations_crud
from schemas import access_tokens as access_tokens_schema, users as users_schema
from constants import (
    USER_NOT_ACTIVE,
)
from dependencies import get_db

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def authenticate_user(username: str, password: str, db: Session):
    """Get the user from the database and verify the password"""
    # Get the user from the database
    user = users_crud.authenticate_user(username, password, db)

    # Check if the user exists and if the password is correct and if not return False
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return the user if the password is correct
    return user


def get_current_user(db: Session, user_id: int):
    """Get the current user from the token and then queries the database to get the user data"""
    # Get the user from the database
    user = users_crud.get_user_by_id(user_id, db)

    # If the user does not exist raise the exception
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials (user not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(user.id, db)

    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials (user integrations not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user_integrations.strava_token is None:
        user.is_strava_linked = 0
    else:
        user.is_strava_linked = 1

    # Return the user
    return user


@router.post("/token", tags=["session"])
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    do_not_expire: bool = False,
    db: Session = Depends(get_db),
) -> access_tokens_schema.AccessToken:
    user = authenticate_user(form_data.username, form_data.password, db)

    if user.is_active == USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expire = None
    if do_not_expire:
        expire = datetime.utcnow() + timedelta(days=90)

    access_token = access_tokens_schema.create_access_token(
        db,
        data={"sub": user.username, "id": user.id, "access_type": user.access_type},
        expires_delta=expire,
    )

    return access_tokens_schema.AccessToken(access_token=access_token, token_type="bearer")


@router.get("/users/me", response_model=users_schema.UserMe, tags=["session"])
async def read_users_me(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
):
    # Validate the token
    access_tokens_schema.validate_token_expiration(db, token)

    # Get the user id from the payload
    user_id = access_tokens_schema.get_token_user_id(token)
    
    return get_current_user(db, user_id)
