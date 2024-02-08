import logging

import models

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def get_acess_tokens_by_user_id(user_id: int, db: Session):
    try:
        access_tokens = (
            db.query(models.AccessToken)
            .filter(models.AccessToken.user_id == user_id)
            .all()
        )
        if access_tokens is None:
            # If the user was not found, return a 404 Not Found error
            return None

        return access_tokens
    except Exception as err:
        # Log the exception
        logger.error(f"Error in get_acess_tokens_by_user_id: {err}", exc_info=True)
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def create_access_token(token, db: Session):
    try:
        # Create a new access token in the database
        db_access_token = models.AccessToken(
            token=token.token,
            user_id=token.user_id,
            created_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            expires_at=token.expires_at,
        )

        # Add the access token to the database and commit the transaction
        db.add(db_access_token)
        db.commit()
        db.refresh(db_access_token)

        # return the access token
        return db_access_token
    except Exception as err:
        # Handle database-related exceptions
        db.rollback()  # Rollback the transaction to maintain database consistency

        # Log the exception
        logger.error(f"Error in create_access_token: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_access_token(token: str, db: Session):
    try:
        # Delete the access token from the database
        db_access_token = (
            db.query(models.AccessToken)
            .filter(models.AccessToken.token == token)
            .delete()
        )

        # Commit the transaction to the database
        if db_access_token:
            db.delete(db_access_token)
            db.commit()
            logger.info(f"{db_access_token} access tokens deleted from the database")
            return db_access_token
        else:
            # If the access token was not found, return a 404 Not Found error
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Access token not found",
            )
    except Exception as err:
        # Handle database-related exceptions
        db.rollback()  # Rollback the transaction to maintain database consistency

        # Log the exception
        logger.error(f"Error in delete_access_token: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def delete_access_tokens(expiration_time: str, db: Session):
    try:
        # Delete the access tokens from the database
        db_access_tokens = (
            db.query(models.AccessToken)
            .filter(models.AccessToken.created_at < expiration_time)
            .delete()
        )

        # Commit the transaction to the database
        if db_access_tokens:
            db.commit()
            logger.info(f"{db_access_tokens} access tokens deleted from the database")
            return db_access_tokens
        else:
            # If no access tokens were found, log the event and return 0
            logger.info("0 access tokens deleted from the database")
    except Exception as err:
        # Handle database-related exceptions
        db.rollback()  # Rollback the transaction to maintain database consistency

        # Log the exception
        logger.error(f"Error in delete_access_tokens: {err}", exc_info=True)

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
