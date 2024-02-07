import logging

from datetime import datetime, timedelta
from typing import Annotated, Callable

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from crud import crud_user_integrations, crud_users
from schemas import schema_access_tokens, schema_users
from constants import (
    USER_NOT_ACTIVE,
)
from dependencies import dependencies_database, dependencies_session

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def authenticate_user(username: str, password: str, db: Session):
    # Get the user from the database
    user = crud_users.authenticate_user(username, password, db)

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
    # Get the user from the database
    user = crud_users.get_user_by_id(user_id, db)

    # If the user does not exist raise the exception
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials (user not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_integrations = crud_user_integrations.get_user_integrations_by_user_id(
        user.id, db
    )

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


@router.post(
    "/token", response_model=schema_access_tokens.AccessToken, tags=["session"]
)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    do_not_expire: bool = False,
    db: Session = Depends(dependencies_database.get_db),
):
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

    access_token = schema_access_tokens.create_access_token(
        db,
        data={"sub": user.username, "id": user.id, "access_type": user.access_type},
        expires_delta=expire,
    )

    return schema_access_tokens.AccessToken(
        access_token=access_token, token_type="bearer"
    )


@router.get("/users/me", response_model=schema_users.UserMe, tags=["session"])
async def read_users_me(
    user_id: Annotated[int, Depends(dependencies_session.validate_token_and_get_authenticated_user_id)],
    db: Session = Depends(dependencies_database.get_db),
):
    return get_current_user(db, user_id)


@router.get("/validate_token", tags=["session"])
async def validate_token(
    validate_token: Callable = Depends(dependencies_session.validate_token),
    db: Session = Depends(dependencies_database.get_db),
):
    # Return None if the token is valid
    return None