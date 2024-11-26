from typing import Annotated, Callable

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

import core.database as core_database

# Define the API router
router = APIRouter()


@router.post("/token")
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    client_type: str = Depends(session_security.header_client_type_scheme),
):
    user = session_utils.authenticate_user(form_data.username, form_data.password, db)

    if user.is_active == session_constants.USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if client_type == "web":
        response = session_utils.create_response_with_tokens(response, user)
        return {"message": "Login successful"}
    elif client_type == "mobile":
        acces_token, refresh_token = session_utils.create_tokens(user)
        return {"access_token": acces_token, "refresh_token": refresh_token}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh")
async def refresh_token(
    response: Response,
    validate_refresh_token: Annotated[
        Callable, Depends(session_security.validate_refresh_token)
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_refresh_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    client_type: str = Depends(session_security.header_client_type_scheme),
):
    # get user
    user = users_crud.get_user_by_id(token_user_id, db)

    if user.is_active == session_constants.USER_NOT_ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if client_type == "web":
        response = session_utils.create_response_with_tokens(response, user)
        return {"message": "Token refreshed successfully"}
    elif client_type == "mobile":
        acces_token, refresh_token = session_utils.create_tokens(user)
        return {"access_token": acces_token, "refresh_token": refresh_token}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout")
async def logout(
    response: Response,
    client_type: str = Depends(session_security.header_client_type_scheme),
):
    if client_type == "web":
        # Clear the cookies by setting their expiration to the past
        response.delete_cookie(key="endurain_access_token", path="/")
        response.delete_cookie(key="endurain_refresh_token", path="/")
        # response.delete_cookie(key="endurain_csrf_token", path="/")
        return {"message": "Logout successful"}
    elif client_type == "mobile":
        return {"message": "Logout successful"}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )
