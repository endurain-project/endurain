from typing import Annotated, Callable

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Response,
    Request,
    Security,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import session.utils as session_utils
import session.security as session_security
import session.constants as session_constants
import session.crud as session_crud
import session.schema as session_schema

import users.user.crud as users_crud
import users.user.utils as users_utils

import core.database as core_database

# Define the API router
router = APIRouter()


@router.post("/token")
async def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    client_type: Annotated[str, Depends(session_security.header_client_type_scheme)],
):
    user = session_utils.authenticate_user(form_data.username, form_data.password, db)

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Create the tokens
    access_token, refresh_token, csrf_token = session_utils.create_tokens(user)

    if client_type == "web":
        # create response with tokens
        response = session_utils.create_response_with_tokens(
            response, access_token, refresh_token, csrf_token
        )

        # Create the session and store it in the database
        session_id = session_utils.create_session(user, request, refresh_token, db)

        # Return the session_id
        return session_id
    elif client_type == "mobile":
        # Create the session and store it in the database
        session_id = session_utils.create_session(user, request, refresh_token, db)

        # Return the tokens
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "session_id": session_id,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh")
async def refresh_token(
    response: Response,
    request: Request,
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
    refresh_token: Annotated[
        str,
        Depends(session_security.get_and_return_refresh_token),
    ],
    client_type: Annotated[str, Depends(session_security.header_client_type_scheme)],
):
    # Get the session from the database
    session = session_crud.get_session_by_refresh_token(refresh_token, db)

    # Check if the session was found
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # get user
    user = users_crud.get_user_by_id(token_user_id, db)

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Create the tokens
    new_access_token, new_refresh_token, new_csrf_token = session_utils.create_tokens(
        user
    )

    if client_type == "web":
        response = session_utils.create_response_with_tokens(
            response, new_access_token, new_refresh_token, new_csrf_token
        )

        # Edit the session and store it in the database
        session_utils.edit_session(session, request, new_refresh_token, db)

        # Return the tokens and a success message
        return {"Token refreshed successfully"}
    elif client_type == "mobile":
        # Edit the session and store it in the database
        session_utils.edit_session(session, request, new_refresh_token, db)

        # Return the tokens
        return {"access_token": new_access_token, "refresh_token": new_refresh_token}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout")
async def logout(
    response: Response,
    refresh_token: Annotated[
        str,
        Depends(session_security.get_and_return_refresh_token),
    ],
    client_type: Annotated[str, Depends(session_security.header_client_type_scheme)],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_refresh_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the session from the database
    session = session_crud.get_session_by_refresh_token(refresh_token, db)

    # Check if the session was found
    if session is not None:
        # Delete the session from the database
        session_crud.delete_session(session.id, token_user_id, db)

    if client_type == "web":
        # Clear the cookies by setting their expiration to the past
        response.delete_cookie(key="endurain_access_token", path="/")
        response.delete_cookie(key="endurain_refresh_token", path="/")
        response.delete_cookie(key="endurain_csrf_token", path="/")
        return {"message": "Logout successful"}
    elif client_type == "mobile":
        return {"message": "Logout successful"}
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/sessions/user/{user_id}")
async def read_sessions_user(
    user_id: int,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["sessions:read"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the sessions from the database
    return session_crud.get_user_sessions(user_id, db)


@router.delete("/sessions/{session_id}/user/{user_id}")
async def delete_session_user(
    session_id: str,
    user_id: int,
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["sessions:write"])
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Delete the session from the database
    return session_crud.delete_session(session_id, user_id, db)


@router.post("/password-reset/request")
async def request_password_reset(
    request_data: session_schema.PasswordResetRequest,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Request a password reset via email"""
    try:
        success = await session_utils.send_password_reset_email(request_data.email, db)
        # Always return success to not reveal if email exists
        return {"message": "If the email exists in our system, a password reset link has been sent."}
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process password reset request"
        )


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    confirm_data: session_schema.PasswordResetConfirm,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Confirm password reset with token"""
    # Check if the password meets the complexity requirements
    is_valid, message = session_security.is_password_complexity_valid(
        confirm_data.new_password
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    
    # Use the token to reset password
    success = session_utils.use_password_reset_token(
        confirm_data.token, 
        confirm_data.new_password, 
        db
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token"
        )
    
    return {"message": "Password reset successful"}
