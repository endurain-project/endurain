import logging

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# import the jwt module from the joserfc package
from joserfc import jwt
from joserfc.jwk import OctKey

from constants import (
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    ADMIN_ACCESS,
)


# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def decode_token(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        # Decode the token and return the payload
        return jwt.decode(token, OctKey.import_key(JWT_SECRET_KEY))
    except Exception:
        # Log the error and raise the exception
        logger.info("Unable to decode token | Returning 401 response")

        # Raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to decode token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_token_expiration(token: Annotated[str, Depends(oauth2_scheme)]):
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
        logger.info("Token expired during validation | Returning 401 response")

        # Raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token no longer valid",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_scopes(token: Annotated[str, Depends(oauth2_scheme)]):
    # Decode the token
    payload = decode_token(token)

    try:
        # Get the scopes from the payload and return it
        return payload.claims["scopes"]
    except Exception:
        # Log the error and raise the exception
        logger.info("Scopes not present in token | Returning 401 response")

        # Raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Scopes not present in token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_user_id(token: Annotated[str, Depends(oauth2_scheme)]):
    # Decode the token
    payload = decode_token(token)

    try:
        # Get the user id from the payload and return it
        return payload.claims["id"]
    except Exception:
        # Log the error and raise the exception
        logger.info("Claim with user ID not present in token | Returning 401 response")

        # Raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Claim with user ID not present in token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_access_type(token: Annotated[str, Depends(oauth2_scheme)]):
    # Decode the token
    payload = decode_token(token)

    try:
        # Get the user access_type from the payload and return it
        return payload.claims["access_type"]
    except Exception:
        # Log the error and raise the exception
        logger.info(
            "Claim with user access Type not present in token | Returning 401 response"
        )

        # Raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Claim with user access Type not present in token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_token_admin_access(token: Annotated[str, Depends(oauth2_scheme)]):
    if get_token_access_type(token) != ADMIN_ACCESS:
        # Raise an HTTPException with a 403 Forbidden status code
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized Access - Admin Access Required",
        )


def create_token(data: dict):
    # Encode the data and return the token
    return jwt.encode({"alg": JWT_ALGORITHM}, data.copy(), JWT_SECRET_KEY)