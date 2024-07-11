import logging

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Response,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import session.utils as session_utils
import session.security as session_security
import session.constants as session_constants

import users.crud as users_crud

import database

# from constants import (
#    USER_NOT_ACTIVE,
# )

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


@router.post("/token")
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    user = session_utils.authenticate_user(form_data.username, form_data.password, db)

    if user.is_active == session_constants.USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response = session_utils.create_response_with_tokens(response, user)

    return {"message": "Login successful"}


@router.post("/refresh")
async def refresh_token(
    response: Response,
    user_id: Annotated[
        int,
        Depends(session_security.validate_refresh_token_and_get_authenticated_user_id),
    ],
    db: Annotated[
        Session,
        Depends(database.get_db),
    ],
):
    # get user
    user = users_crud.get_user_by_id(user_id, db)

    if user.is_active == session_constants.USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    response = session_utils.create_response_with_tokens(response, user)

    return {"message": "Token refreshed successfully"}


@router.post("/logout")
async def logout(
    response: Response,
):
    # Clear the cookies by setting their expiration to the past
    response.delete_cookie(key="endurain_access_token", path="/")
    response.delete_cookie(key="endurain_refresh_token", path="/")
    # response.delete_cookie(key="ctr_csrf_token", path="/")

    return {"message": "Logout successful"}
