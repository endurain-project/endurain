import os
import secrets
import hashlib

from datetime import datetime, timedelta, timezone
from fastapi import (
    HTTPException,
    status,
    Response,
    Request,
)
from user_agents import parse
from uuid import uuid4

from sqlalchemy.orm import Session

import session.security as session_security
import session.constants as session_constants
import session.schema as session_schema
import session.crud as session_crud

import users.user.crud as users_crud
import users.user.schema as users_schema

import core.email as core_email


def create_session_object(
    user: users_schema.User,
    request: Request,
    refresh_token: str,
    refresh_token_exp: datetime,
) -> session_schema.UsersSessions:
    user_agent = get_user_agent(request)
    parsed_ua = parse_user_agent(user_agent)

    return session_schema.UsersSessions(
        id=str(uuid4()),
        user_id=user.id,
        refresh_token=refresh_token,
        ip_address=get_ip_address(request),
        device_type=parsed_ua["device_type"],
        operating_system=parsed_ua["operating_system"],
        operating_system_version=parsed_ua["operating_system_version"],
        browser=parsed_ua["browser"],
        browser_version=parsed_ua["browser_version"],
        created_at=datetime.now(timezone.utc),
        expires_at=refresh_token_exp,
    )


def edit_session_object(
    request: Request,
    refresh_token: str,
    refresh_token_exp: datetime,
    session: Session,
) -> session_schema.UsersSessions:
    user_agent = get_user_agent(request)
    parsed_ua = parse_user_agent(user_agent)

    return session_schema.UsersSessions(
        id=session.id,
        user_id=session.user_id,
        refresh_token=refresh_token,
        ip_address=get_ip_address(request),
        device_type=parsed_ua["device_type"],
        operating_system=parsed_ua["operating_system"],
        operating_system_version=parsed_ua["operating_system_version"],
        browser=parsed_ua["browser"],
        browser_version=parsed_ua["browser_version"],
        created_at=session.created_at,
        expires_at=refresh_token_exp,
    )


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


def create_tokens(user: users_schema.User):
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
            "scopes": scopes,
            "exp": datetime.now(timezone.utc)
            + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        },
    )

    csrf_token = session_security.create_csrf_token()

    return access_token, refresh_token, csrf_token


def create_response_with_tokens(
    response: Response, access_token: str, refresh_token: str, csrf_token: str
):
    secure = False
    if os.environ.get("FRONTEND_PROTOCOL") == "https":
        secure = True

    # Set the cookies with the tokens
    response.set_cookie(
        key="endurain_access_token",
        value=access_token,
        expires=datetime.now(timezone.utc)
        + timedelta(minutes=session_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
        httponly=True,
        path="/",
        secure=secure,
        samesite="Lax",
    )
    response.set_cookie(
        key="endurain_refresh_token",
        value=refresh_token,
        expires=datetime.now(timezone.utc)
        + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        httponly=True,
        path="/",
        secure=secure,
        samesite="Lax",
    )
    response.set_cookie(
        key="endurain_csrf_token",
        value=csrf_token,
        httponly=False,
        path="/",
        secure=secure,
        samesite="Lax",
    )

    # Return the response
    return response


def create_session(
    user: users_schema.User,
    request: Request,
    refresh_token: str,
    db: Session,
):
    # Create a new session
    new_session = create_session_object(
        user,
        request,
        refresh_token,
        datetime.now(timezone.utc)
        + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )

    # Add the session to the database
    session_crud.create_session(new_session, db)

    # Return the response
    return new_session.id


def edit_session(
    session: session_schema.UsersSessions,
    request: Request,
    new_refresh_token: str,
    db: Session,
):
    # Update the session
    edit_session = edit_session_object(
        request,
        new_refresh_token,
        datetime.now(timezone.utc)
        + timedelta(days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        session,
    )

    # Update the session in the database
    session_crud.edit_session(edit_session, db)


def get_user_agent(request: Request) -> str:
    return request.headers.get("user-agent")


def get_ip_address(request: Request) -> str:
    return request.client.host


def parse_user_agent(user_agent: str):
    ua = parse(user_agent)
    device_type = "Mobile" if ua.is_mobile else "Tablet" if ua.is_tablet else "PC"
    operating_system = ua.os.family
    operating_system_version = ua.os.version_string
    browser = ua.browser.family
    browser_version = ua.browser.version_string

    return {
        "device_type": device_type,
        "operating_system": operating_system,
        "operating_system_version": operating_system_version,
        "browser": browser,
        "browser_version": browser_version,
    }


def generate_password_reset_token() -> tuple[str, str]:
    """Generate a secure password reset token and its hash"""
    # Generate a random 32-byte token
    token = secrets.token_urlsafe(32)
    
    # Create a hash of the token for database storage
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    return token, token_hash


def create_password_reset_token(user_id: int, db: Session) -> str:
    """Create a password reset token for a user"""
    # Generate token and hash
    token, token_hash = generate_password_reset_token()
    
    # Create token object
    reset_token = session_schema.PasswordResetToken(
        id=str(uuid4()),
        user_id=user_id,
        token_hash=token_hash,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),  # 1 hour expiration
        used=0
    )
    
    # Save to database
    session_crud.create_password_reset_token(reset_token, db)
    
    # Return the plain token (not the hash)
    return token


async def send_password_reset_email(email: str, db: Session) -> bool:
    """Send password reset email to user"""
    # Check if email service is configured
    if not core_email.email_service.is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured"
        )
    
    # Find user by email
    user = users_crud.get_user_by_email(email, db)
    if not user:
        # Don't reveal if email exists or not for security
        return True
    
    # Check if user is active
    if user.is_active != 1:
        # Don't reveal if user is inactive for security
        return True
    
    # Generate password reset token
    token = create_password_reset_token(user.id, db)
    
    # Get frontend host
    frontend_host = os.getenv("ENDURAIN_HOST", "http://localhost:3000")
    
    # Send email
    success = await core_email.email_service.send_password_reset_email(
        to_email=email,
        user_name=user.name,
        reset_token=token,
        frontend_host=frontend_host
    )
    
    return success


def validate_password_reset_token(token: str, db: Session) -> tuple[bool, int | None]:
    """Validate a password reset token and return user_id if valid"""
    # Hash the provided token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Find token by hash
    # Note: We need to search by hash, but our current get_password_reset_token searches by id
    # We need to modify the CRUD or create a new function
    from sqlalchemy import and_
    import session.models as session_models
    
    db_token = (
        db.query(session_models.PasswordResetToken)
        .filter(
            and_(
                session_models.PasswordResetToken.token_hash == token_hash,
                session_models.PasswordResetToken.used == 0,
                session_models.PasswordResetToken.expires_at > datetime.now(timezone.utc)
            )
        )
        .first()
    )
    
    if not db_token:
        return False, None
    
    return True, db_token.user_id


def use_password_reset_token(token: str, new_password: str, db: Session) -> bool:
    """Use a password reset token to change password"""
    # Validate token
    is_valid, user_id = validate_password_reset_token(token, db)
    if not is_valid or user_id is None:
        return False
    
    # Hash the provided token to find the database record
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Find and mark token as used
    from sqlalchemy import and_
    import session.models as session_models
    
    db_token = (
        db.query(session_models.PasswordResetToken)
        .filter(
            and_(
                session_models.PasswordResetToken.token_hash == token_hash,
                session_models.PasswordResetToken.used == 0
            )
        )
        .first()
    )
    
    if not db_token:
        return False
    
    # Update user password
    try:
        users_crud.edit_user_password(user_id, new_password, db)
        
        # Mark token as used
        session_crud.mark_password_reset_token_used(db_token.id, db)
        
        return True
    except Exception:
        return False
