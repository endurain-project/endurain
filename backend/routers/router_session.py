import logging
import bcrypt

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Response,
    Request,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from crud import crud_users
from schemas import schema_users
from constants import (
    USER_NOT_ACTIVE,
    REGULAR_ACCESS,
    REGULAR_ACCESS_SCOPES,
    ADMIN_ACCESS_SCOPES,
    SCOPES_DICT,
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
)
from dependencies import (
    dependencies_database,
    dependencies_session,
    dependencies_security,
)

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token",
    scopes=SCOPES_DICT,
)

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def hash_password(password: str):
    # Hash the password and return it
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(plain_password: str, hashed_password: str):
    # Check if the password is equal to the hashed password
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def authenticate_user(username: str, password: str, db: Session):
    # Get the user from the database
    user = crud_users.authenticate_user(username, db)

    # Check if the user exists and if the hashed_password is correct and if not return False
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return the user if the hashed_password is correct
    return user


def create_response_with_tokens(response: Response, user: schema_users.User):
    # Check user access level and set scopes accordingly
    if user.access_type == REGULAR_ACCESS:
        scopes = REGULAR_ACCESS_SCOPES
    else:
        scopes = ADMIN_ACCESS_SCOPES

    # Create the access and refresh tokens
    access_token = dependencies_security.create_token(
        data={
            "sub": user.username,
            "scopes": scopes,
            "id": user.id,
            "access_type": user.access_type,
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        },
    )

    refresh_token = dependencies_security.create_token(
        data={
            "sub": user.username,
            "scopes": "scopes",
            "id": user.id,
            "access_type": user.access_type,
            "exp": datetime.now(timezone.utc)
            + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        },
    )

    # Set the cookies with the tokens
    response.set_cookie(
        key="endurain_access_token",
        value=access_token,
        expires=datetime.now(timezone.utc)
        + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        httponly=True,
        path="/",
        secure=False,
        samesite="None",
    )
    response.set_cookie(
        key="endurain_refresh_token",
        value=refresh_token,
        expires=datetime.now(timezone.utc)
        + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        httponly=True,
        path="/",
        secure=False,
        samesite="None",
    )

    # Set the user id in a cookie
    response.set_cookie(
        key="endurain_logged_user_id",
        value=user.id,
        httponly=False,
    )

    # Return the response
    return response


@router.post("/token", tags=["session"])
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(dependencies_database.get_db),
):
    user = authenticate_user(form_data.username, form_data.password, db)

    if user.is_active == USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response = create_response_with_tokens(response, user)

    return {"message": "Login successful"}


@router.post("/refresh", tags=["session"])
async def refresh_token(
    response: Response,
    request: Request,
    user_id: Annotated[
        int,
        Depends(
            dependencies_session.validate_refresh_token_and_get_authenticated_user_id
        ),
    ],
    db: Session = Depends(dependencies_database.get_db),
):
    # get user
    user = crud_users.get_user_by_id(user_id, db)

    if user.is_active == USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response = create_response_with_tokens(response, user)

    return {"message": "Token refreshed successfully"}
