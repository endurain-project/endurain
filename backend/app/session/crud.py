from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import session.models as session_models
import session.schema as session_schema

import core.logger as core_logger


def get_user_sessions(user_id: int, db: Session):
    try:
        db_sessions = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.user_id == user_id)
            .all()
        )

        # If the no session was found, return None
        if db_sessions is None:
            return None

        # Return the sessions
        return db_sessions
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(f"Error in get_user_sessions: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_session_by_refresh_token(refresh_token: str, db: Session):
    try:
        # Get the session from the database
        db_session = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.refresh_token == refresh_token)
            .first()
        )

        # If the session was not found, return None
        if db_session is None:
            return None

        # Return the session
        return db_session
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_session_by_refresh_token: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_session(session: session_schema.UsersSessions, db: Session):
    try:
        # Create a new session
        db_session = session_models.UsersSessions(
            id=session.id,
            user_id=session.user_id,
            refresh_token=session.refresh_token,
            ip_address=session.ip_address,
            device_type=session.device_type,
            operating_system=session.operating_system,
            operating_system_version=session.operating_system_version,
            browser=session.browser,
            browser_version=session.browser_version,
            created_at=session.created_at,
            expires_at=session.expires_at,
        )

        # Add the user to the database
        db.add(db_session)
        db.commit()
        db.refresh(db_session)

        # Return the user
        return db_session
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_session: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def edit_session(session: session_schema.UsersSessions, db: Session):
    try:
        # Get the session from the database
        db_session = (
            db.query(session_models.UsersSessions)
            .filter(session_models.UsersSessions.id == session.id)
            .first()
        )

        # Dictionary of the fields to update if they are not None
        session_data = session.model_dump(exclude_unset=True)
        # Iterate over the fields and update the db_session dynamically
        for key, value in session_data.items():
            setattr(db_session, key, value)

        # Commit the transaction
        db.commit()
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in edit_session: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_session(session_id: str, user_id: int, db: Session):
    try:
        # Delete the session
        num_deleted = (
            db.query(session_models.UsersSessions)
            .filter(
                session_models.UsersSessions.id == session_id,
                session_models.UsersSessions.user_id == user_id,
            )
            .delete()
        )

        # Check if the session was found and deleted
        if num_deleted == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session ID {session_id} not found",
            )

        # Commit the transaction
        db.commit()
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in delete_session: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_password_reset_token(token: session_schema.PasswordResetToken, db: Session):
    try:
        # Create a new password reset token
        db_token = session_models.PasswordResetToken(
            id=token.id,
            user_id=token.user_id,
            token_hash=token.token_hash,
            created_at=token.created_at,
            expires_at=token.expires_at,
            used=token.used,
        )

        # Add the token to the database
        db.add(db_token)
        db.commit()
        db.refresh(db_token)

        # Return the token
        return db_token
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(f"Error in create_password_reset_token: {err}", "error", exc=err)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_password_reset_token(token_id: str, db: Session):
    try:
        # Get the token from the database
        db_token = (
            db.query(session_models.PasswordResetToken)
            .filter(session_models.PasswordResetToken.id == token_id)
            .first()
        )

        # Return the token (can be None if not found)
        return db_token
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in get_password_reset_token: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def mark_password_reset_token_used(token_id: str, db: Session):
    try:
        # Get the token from the database
        db_token = (
            db.query(session_models.PasswordResetToken)
            .filter(session_models.PasswordResetToken.id == token_id)
            .first()
        )

        if db_token:
            # Mark the token as used
            db_token.used = 1
            db.commit()

        return db_token
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in mark_password_reset_token_used: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_expired_password_reset_tokens(db: Session):
    """Delete all expired password reset tokens"""
    try:
        from datetime import datetime, timezone
        
        # Delete expired tokens
        num_deleted = (
            db.query(session_models.PasswordResetToken)
            .filter(session_models.PasswordResetToken.expires_at < datetime.now(timezone.utc))
            .delete()
        )

        # Commit the transaction
        db.commit()
        
        return num_deleted
    except Exception as err:
        # Rollback the transaction
        db.rollback()

        # Log the exception
        core_logger.print_to_log(
            f"Error in delete_expired_password_reset_tokens: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
