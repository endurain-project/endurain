from datetime import datetime, timedelta, timezone
from fastapi import (
    HTTPException,
    status,
    Response,
)

from sqlalchemy.orm import Session

import session.security as session_security
import session.constants as session_constants

import users.crud as users_crud
import users.schema as users_schema

# from constants import (
#    REGULAR_ACCESS,
#    REGULAR_ACCESS_SCOPES,
#    ADMIN_ACCESS_SCOPES,
#    JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
#    JWT_REFRESH_TOKEN_EXPIRE_DAYS,
# )


def authenticate_user(username: str, password: str, db: Session):
    # Get the user from the database
    user = users_crud.authenticate_user(username, db)

    # Check if the user exists and if the hashed_password is correct and if not return False
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not session_security.verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return the user if the hashed_password is correct
    return user


def create_response_with_tokens(response: Response, user: users_schema.User):
    # Check user access level and set scopes accordingly
    if user.access_type == session_constants.REGULAR_ACCESS:
        scopes = session_constants.REGULAR_ACCESS_SCOPES
    else:
        scopes = session_constants.ADMIN_ACCESS_SCOPES

    # Create the access and refresh tokens
    access_token = session_security.create_token(
        data={
            "sub": user.id,
            "scopes": scopes,
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=session_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        },
    )

    refresh_token = session_security.create_token(
        data={
            "sub": user.id,
            "scopes": "scopes",
            "exp": datetime.now(timezone.utc)
            + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        },
    )

    # Set the cookies with the tokens
    response.set_cookie(
        key="endurain_access_token",
        value=access_token,
        expires=datetime.now(timezone.utc)
        + timedelta(minutes=session_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        httponly=True,
        path="/",
        secure=False,
        samesite="None",
    )
    response.set_cookie(
        key="endurain_refresh_token",
        value=refresh_token,
        expires=datetime.now(timezone.utc)
        + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        httponly=True,
        path="/",
        secure=False,
        samesite="None",
    )

    # Set the user id in a cookie
    # response.set_cookie(
    #    key="endurain_logged_user_id",
    #    value=user.id,
    #    httponly=False,
    # )

    # Return the response
    return response
