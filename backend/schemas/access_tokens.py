import logging

from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from crud import access_tokens as access_tokens_crud
from constants import (
    JWT_EXPIRATION_IN_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    ADMIN_ACCESS,
)


class AccessToken(BaseModel):
    """Access token schema"""

    access_token: str
    token_type: str


class Token(BaseModel):
    """Token schema"""

    user_id: int | None = None
    expires_at: str | None = None


class TokenData(Token):
    """Token data schema"""

    access_type: int | None = None


class CreateToken(Token):
    """Create token schema"""

    token: str


# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def decode_token(token: str = Depends(oauth2_scheme)):
    """Decode the token and return the payload"""
    return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])


def validate_token_expiration(db: Session, token: str = Depends(oauth2_scheme)):
    """Validate the token and check if it is expired"""
    # Try to decode the token and check if it is expired
    try:
        # Decode the token
        payload = decode_token(token)

        # Get the expiration timestamp from the payload
        expiration_timestamp = payload.get("exp")

        # If the expiration timestamp is None or if it is less than the current time raise an exception and log it
        if (
            expiration_timestamp is None
            or datetime.utcfromtimestamp(expiration_timestamp) < datetime.utcnow()
        ):
            logger.warning(
                "Token expired | Will force remove_expired_tokens to run | Returning 401 response"
            )
            remove_expired_tokens(db)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token no longer valid",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except jwt.ExpiredSignatureError:
        # Log the error and raise the exception
        logger.info(
            "Token expired during validation | Will force remove_expired_tokens to run | Returning 401 response"
        )
        remove_expired_tokens(db)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as err:
        # Log the error and raise the exception
        logger.error(
            f"Error in validate_token_expiration on payload validation: {err}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def get_token_user_id(token: str = Depends(oauth2_scheme)):
    """Get the user id from the token"""
    # Decode the token
    payload = decode_token(token)

    # Get the user id from the payload
    user_id = payload.get("id")

    if user_id is None:
        # If the user id is None raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return the user id
    return user_id


def get_token_access_type(token: str = Depends(oauth2_scheme)):
    """Get the admin access from the token"""
    # Decode the token
    payload = decode_token(token)

    # Get the admin access from the payload
    access_type = payload.get("access_type")

    if access_type is None:
        # If the access type is None raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Return the access type
    return access_type


def validate_token_admin_access(token: str = Depends(oauth2_scheme)):
    if get_token_access_type(token) != ADMIN_ACCESS:
        # Raise an HTTPException with a 403 Forbidden status code
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized Access - Admin Access Required",
        )


def create_access_token(
    db: Session, data: dict, expires_delta: timedelta | None = None
):
    """Creates a new JWT token with the provided data and expiration time"""
    # Create a copy of the data to encode
    to_encode = data.copy()

    # If an expiration time is provided, calculate the expiration time
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=JWT_EXPIRATION_IN_MINUTES
        )

    # Add the expiration time to the data to encode
    to_encode.update({"exp": expire})

    # Encode the data and return the token
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    # Save the token in the database
    db_access_token = access_tokens_crud.create_access_token(
        CreateToken(
            token=encoded_jwt,
            user_id=data.get("id"),
            expires_at=expire.strftime("%Y-%m-%dT%H:%M:%S"),
        ),
        db,
    )
    if db_access_token:
        # Return the token
        return encoded_jwt
    else:
        # If the token could not be saved in the database return None
        return None


def remove_expired_tokens(db: Session):
    """Remove expired tokens from the database"""
    # Calculate the expiration time
    expiration_time = datetime.utcnow() - timedelta(minutes=JWT_EXPIRATION_IN_MINUTES)

    # Delete the expired tokens from the database
    rows_deleted = access_tokens_crud.delete_access_tokens(expiration_time, db)

    # Log the number of tokens deleted
    logger.info(f"{rows_deleted} access tokens deleted from the database")
