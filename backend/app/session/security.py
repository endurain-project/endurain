import bcrypt
import logging

from typing import Annotated
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    OAuth2PasswordBearer,
    SecurityScopes,
    APIKeyHeader,
    APIKeyCookie,
)

# import the jwt module from the joserfc package
from joserfc import jwt
from joserfc.jwk import OctKey

import session.constants as session_constants

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token",
    scopes=session_constants.SCOPES_DICT,
    auto_error=False,
)

# Define the API key header for the client type
header_client_type_scheme = APIKeyHeader(name="X-Client-Type")

# Define the API key cookie for the access token
cookie_access_token_scheme = APIKeyCookie(
    name="endurain_access_token",
    auto_error=False,
)
# Define the API key cookie for the refresh token
cookie_refresh_token_scheme = APIKeyCookie(
    name="endurain_refresh_token",
    auto_error=False,
)

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")


def hash_password(password: str):
    # Hash the password and return it
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())


def verify_password(plain_password: str, hashed_password: str):
    # Check if the password is equal to the hashed password
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def decode_token(token: Annotated[str, Depends(oauth2_scheme)]):
    try:
        # Decode the token and return the payload
        return jwt.decode(token, OctKey.import_key(session_constants.JWT_SECRET_KEY))
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


def get_token_user_id(token: Annotated[str, Depends(oauth2_scheme)]):
    # Decode the token
    payload = decode_token(token)

    try:
        # Get the user id from the payload and return it
        return payload.claims["sub"]
    except Exception:
        # Log the error and raise the exception
        logger.info("Claim with user ID not present in token | Returning 401 response")

        # Raise an HTTPException with a 401 Unauthorized status code
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Claim with user ID not present in token",
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


def create_token(data: dict):
    # Encode the data and return the token
    return jwt.encode(
        {"alg": session_constants.JWT_ALGORITHM},
        data.copy(),
        session_constants.JWT_SECRET_KEY,
    )


## ACCESS TOKEN VALIDATION
def get_access_token(
    noncookie_access_token: Annotated[str, Depends(oauth2_scheme)],
    cookie_access_token: str = Depends(cookie_access_token_scheme),
    client_type: str = Depends(header_client_type_scheme),
):
    if noncookie_access_token is None and cookie_access_token is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if client_type == "web":
        return cookie_access_token
    elif client_type == "mobile":
        return noncookie_access_token
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_access_token(
    # access_token: Annotated[str, Depends(get_access_token_from_cookies)]
    access_token: Annotated[str, Depends(get_access_token)]
):
    # Validate the token expiration
    validate_token_expiration(access_token)


def get_user_id_from_access_token(
    access_token: Annotated[str, Depends(get_access_token)]
):
    # Return the user ID associated with the token
    return get_token_user_id(access_token)


def get_and_return_access_token(
    access_token: Annotated[str, Depends(get_access_token)],
):
    # Return token
    return access_token


## REFRESH TOKEN VALIDATION
def get_refresh_token(
    noncookie_refresh_token: Annotated[str, Depends(oauth2_scheme)],
    cookie_refresh_token: str = Depends(cookie_refresh_token_scheme),
    client_type: str = Depends(header_client_type_scheme),
):
    if noncookie_refresh_token is None and cookie_refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if client_type == "web":
        return cookie_refresh_token
    elif client_type == "mobile":
        return noncookie_refresh_token
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_refresh_token_and_get_authenticated_user_id(
    refresh_token: Annotated[str, Depends(get_refresh_token)]
):
    # Return the user ID associated with the token
    return get_token_user_id(refresh_token)


def check_scopes(
    access_token: Annotated[str, Depends(get_access_token)],
    security_scopes: SecurityScopes,
):
    # Get the scopes from the token
    scopes = get_token_scopes(access_token)

    # Check if the token has the required scopes
    for scope in security_scopes.scopes:
        if scope not in scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized Access - Not enough permissions - scope={security_scopes.scopes}",
                headers={
                    "WWW-Authenticate": f'Bearer scope="{security_scopes.scopes}"'
                },
            )
