import logging

from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
#from jose import JWTError, jwt
from joserfc import jwt
from joserfc.jwk import OctKey
from sqlalchemy.orm import Session

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
    # Decode the token and return the payload
    return jwt.decode(token, OctKey.import_key(JWT_SECRET_KEY))


def validate_token_expiration(db: Session, token: str = Depends(oauth2_scheme)):
    # Try to decode the token and check if it is expired
    try:
        # Decode the token
        # Mark exp claim as required
        claims_requests = jwt.JWTClaimsRegistry(exp={"essential": True})

        # decodes the token
        payload = decode_token(token)

        # Validate token exp
        claims_requests.validate(payload.claims)
    except Exception:
        # Log the error and raise the exception
        logger.info(
            "Token expired during validation | Returning 401 response"
        )

        # Raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_user_id(token: str = Depends(oauth2_scheme)):
    # Decode the token
    payload = decode_token(token)

    # Get the user id from the payload
    user_id = payload.claims["id"]

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
    # Decode the token
    payload = decode_token(token)

    # Get the admin access from the payload
    access_type = payload.claims["access_type"]

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
    #encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    encoded_jwt = jwt.encode({"alg": JWT_ALGORITHM}, to_encode, JWT_SECRET_KEY)

    # Return the token
    return encoded_jwt
