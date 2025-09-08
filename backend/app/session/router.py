import email
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
import session.crud as session_crud
import session.schema as session_schema
import session.email_messages as session_email_messages

import users.user.crud as users_crud
import users.user.utils as users_utils
import users.user.schema as users_schema
import users.user_integrations.crud as user_integrations_crud
import users.user_default_gear.crud as user_default_gear_crud
import users.user_privacy_settings.crud as users_privacy_settings_crud

import health_targets.crud as health_targets_crud
import profile.utils as profile_utils
import server_settings.crud as server_settings_crud

import core.database as core_database
import core.apprise as core_apprise

# Define the API router
router = APIRouter()


@router.post("/token")
async def login_for_access_token(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    client_type: Annotated[str, Depends(session_security.header_client_type_scheme)],
    pending_mfa_store: Annotated[
        session_schema.PendingMFALogin, Depends(session_schema.get_pending_mfa_store)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    user = session_utils.authenticate_user(form_data.username, form_data.password, db)

    # Check if the user is active
    users_utils.check_user_is_active(user)

    # Check if MFA is enabled for this user
    if profile_utils.is_mfa_enabled_for_user(user.id, db):
        # Store the user for pending MFA verification
        pending_mfa_store.add_pending_login(form_data.username, user.id)

        # Return MFA required response
        if client_type == "web":
            response.status_code = status.HTTP_202_ACCEPTED
            return session_schema.MFARequiredResponse(
                mfa_required=True,
                username=form_data.username,
                message="MFA verification required",
            )
        if client_type == "mobile":
            return {
                "mfa_required": True,
                "username": form_data.username,
                "message": "MFA verification required",
            }

    # If no MFA required, proceed with normal login
    return await complete_login(response, request, user, client_type, db)


async def complete_login(
    response: Response, request: Request, user, client_type: str, db: Session
):
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


@router.post("/sign-up/request", status_code=201)
async def signup(
    user: users_schema.UserSignup,
    email_service: Annotated[
        core_apprise.AppriseService,
        Depends(core_apprise.get_email_service),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get server settings to check if signup is enabled
    server_settings = server_settings_crud.get_server_settings(db)
    if not server_settings:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server settings not configured",
        )

    # Check if signup is enabled
    if not server_settings.signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User sign-up is not enabled on this server",
        )

    # Generate email verification token if needed
    email_verification_token = None
    email_verification_token_hash = None
    if server_settings.signup_require_email_verification:
        # Generate token and hash
        email_verification_token, email_verification_token_hash = (
            core_apprise.generate_token_and_hash()
        )

    # Create the user in the database
    created_user = users_crud.create_signup_user(
        user, email_verification_token_hash, server_settings, db
    )

    # Create the user integrations in the database
    user_integrations_crud.create_user_integrations(created_user.id, db)

    # Create the user privacy settings
    users_privacy_settings_crud.create_user_privacy_settings(created_user.id, db)

    # Create the user health targets
    health_targets_crud.create_health_targets(created_user.id, db)

    # Create the user default gear
    user_default_gear_crud.create_user_default_gear(created_user.id, db)

    # Return appropriate response based on server configuration
    response_data = {"message": "User created successfully."}

    if server_settings.signup_require_email_verification:
        # Generate sign-up link
        sign_up_link = f"{email_service.frontend_host}/verify-email?token={email_verification_token}"
        # use default email message in English
        subject, html_content, text_content = (
            session_email_messages.get_signup_confirmation_email_en(
                user.name, sign_up_link, email_service
            )
        )
        await email_service.send_email(
            to_emails=[user.email],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
        response_data["message"] = (
            response_data["message"] + " Email sent with verification instructions."
        )
        response_data["email_verification_required"] = True
    if server_settings.signup_require_admin_approval:
        response_data["message"] = (
            response_data["message"] + " Account is pending admin approval."
        )
        response_data["admin_approval_required"] = True
    if (
        not server_settings.signup_require_email_verification
        and not server_settings.signup_require_admin_approval
    ):
        response_data["message"] = response_data["message"] + " You can now log in."
    return response_data


@router.get("/sign-up/confirm")
async def verify_email(
    confirm_data: session_schema.SignUpResetConfirm,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Public endpoint for email verification"""
    # Get server settings
    server_settings = server_settings_crud.get_server_settings(db)
    if not server_settings or not server_settings.signup_require_email_verification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email verification is not enabled",
        )

    # Verify the email
    user = users_crud.verify_user_email(confirm_data.token, db)

    message = "Email verified successfully."
    if user.pending_admin_approval:
        message += " Your account is now pending admin approval."
    else:
        message += " You can now log in."

    return {
        "message": message,
    }


@router.post("/mfa/verify")
async def verify_mfa_and_login(
    response: Response,
    request: Request,
    mfa_request: session_schema.MFALoginRequest,
    client_type: Annotated[str, Depends(session_security.header_client_type_scheme)],
    pending_mfa_store: Annotated[
        session_schema.PendingMFALogin, Depends(session_schema.get_pending_mfa_store)
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Check if there's a pending MFA login for this username
    user_id = pending_mfa_store.get_pending_login(mfa_request.username)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending MFA login found for this username",
        )

    # Verify the MFA code
    if not profile_utils.verify_user_mfa(user_id, mfa_request.mfa_code, db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code"
        )

    # Get the user and complete login
    user = users_crud.get_user_by_id(user_id, db)
    if not user:
        pending_mfa_store.delete_pending_login(mfa_request.username)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check if the user is still active
    users_utils.check_user_is_active(user)

    # Clean up pending login
    pending_mfa_store.delete_pending_login(mfa_request.username)

    # Complete the login
    return await complete_login(response, request, user, client_type, db)


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
