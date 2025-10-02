import bcrypt
import secrets

from typing import Annotated, Union
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

import core.logger as core_logger

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


def is_password_complexity_valid(password) -> tuple[bool, str]:
    # Check for minimum length
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."

    # Check for at least one uppercase letter
    if not any(char.isupper() for char in password):
        return False, "Password must contain at least one uppercase letter."

    # Check for at least one digit
    if not any(char.isdigit() for char in password):
        return False, "Password must contain at least one digit."

    # Check for at least one special character
    special_characters = set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
    if not any(char in special_characters for char in password):
        return False, "Password must contain at least one special character."

    return True, "Password is valid."


def hash_password(password: str) -> str:
    # Explicitly set the cost factor for bcrypt (default is 12, but is set explicitly for clarity)
    cost_factor = 12
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=cost_factor)
    ).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error verifying password: {err}",
            "error",
            exc=err,
            context={"plain_password": "[REDACTED]", "hashed_password": "[REDACTED]"},
        )
        return False


def decode_token(token: Annotated[str, Depends(oauth2_scheme)]) -> dict:
    try:
        # Decode the token and return the payload
        return jwt.decode(token, OctKey.import_key(session_constants.JWT_SECRET_KEY))
    except Exception as err:
        core_logger.print_to_log(
            f"Error decoding token: {err}",
            "error",
            exc=err,
            context={"token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to decode token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def validate_token_expiration(token: Annotated[str, Depends(oauth2_scheme)]) -> None:
    try:
        claims_requests = jwt.JWTClaimsRegistry(
            exp={"essential": True},
            sub={"essential": True},  # Ensure 'sub' claim is required
        )
        payload = decode_token(token)

        # Validate token expiration
        claims_requests.validate(payload.claims)
    except jwt.JWTClaimsError as claims_err:
        core_logger.print_to_log(
            f"JWT claims validation error: {claims_err}",
            "error",
            exc=claims_err,
            context={"token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required claims or is invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error validating token expiration: {err}",
            "error",
            exc=err,
            context={"token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is expired or invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_user_id(token: Annotated[str, Depends(oauth2_scheme)]) -> int:
    try:
        # Decode the token
        payload = decode_token(token)

        # Get the user id from the payload and return it
        return payload.claims["sub"]
    except KeyError as err:
        core_logger.print_to_log(
            f"User ID claim not found in token: {err}",
            "error",
            exc=err,
            context={"token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID claim is missing in the token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error retrieving user ID from token: {err}",
            "error",
            exc=err,
            context={"token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to retrieve user ID from token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_scopes(token: Annotated[str, Depends(oauth2_scheme)]) -> list[str]:
    try:
        # Decode the token
        payload = decode_token(token)

        # Get the scopes from the payload and return it
        return payload.claims["scopes"]
    except KeyError as err:
        core_logger.print_to_log(
            f"Scopes claim not found in token: {err}",
            "error",
            exc=err,
            context={"token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Scopes claim is missing in the token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as err:
        core_logger.print_to_log(
            f"Error retrieving scopes from token: {err}",
            "error",
            exc=err,
            context={"token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to retrieve scopes from token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Helper function to create a CSRF token
def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_token(data: dict) -> str:
    # Encode the data and return the token
    return jwt.encode(
        {"alg": session_constants.JWT_ALGORITHM},
        data.copy(),
        OctKey.import_key(session_constants.JWT_SECRET_KEY),
    )


def get_token(
    noncookie_token: Annotated[Union[str, None], Depends(oauth2_scheme)],
    cookie_token: Union[str, None],
    client_type: str,
    token_type: str,
) -> str:
    if noncookie_token is None and cookie_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"{token_type.capitalize()} token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if client_type == "web":
        return cookie_token
    elif client_type == "mobile":
        return noncookie_token
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid client type",
            headers={"WWW-Authenticate": "Bearer"},
        )


## ACCESS TOKEN VALIDATION
def get_access_token(
    noncookie_access_token: Annotated[Union[str, None], Depends(oauth2_scheme)],
    cookie_access_token: Union[str, None] = Depends(cookie_access_token_scheme),
    client_type: str = Depends(header_client_type_scheme),
) -> str:
    return get_token(noncookie_access_token, cookie_access_token, client_type, "access")


def validate_access_token(
    # access_token: Annotated[str, Depends(get_access_token_from_cookies)]
    access_token: Annotated[str, Depends(get_access_token)],
) -> None:
    try:
        # Validate the token expiration
        validate_token_expiration(access_token)
    except HTTPException as http_err:
        core_logger.print_to_log(
            f"Access token validation failed: {http_err.detail}",
            "error",
            exc=http_err,
            context={"access_token": "[REDACTED]"},
        )
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Unexpected error during access token validation: {err}",
            "error",
            exc=err,
            context={"access_token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during access token validation.",
        )


def get_user_id_from_access_token(
    access_token: Annotated[str, Depends(get_access_token)],
) -> int:
    # Return the user ID associated with the token
    return get_token_user_id(access_token)


def get_and_return_access_token(
    access_token: Annotated[str, Depends(get_access_token)],
) -> str:
    # Return token
    return access_token


## REFRESH TOKEN VALIDATION
def get_refresh_token(
    noncookie_refresh_token: Annotated[Union[str, None], Depends(oauth2_scheme)],
    cookie_refresh_token: Union[str, None] = Depends(cookie_refresh_token_scheme),
    client_type: str = Depends(header_client_type_scheme),
) -> str:
    return get_token(
        noncookie_refresh_token, cookie_refresh_token, client_type, "refresh"
    )


def validate_refresh_token(
    # access_token: Annotated[str, Depends(get_access_token_from_cookies)]
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> None:
    try:
        # Validate the token expiration
        validate_token_expiration(refresh_token)
    except HTTPException as http_err:
        core_logger.print_to_log(
            f"Refresh token validation failed: {http_err.detail}",
            "error",
            exc=http_err,
            context={"refresh_token": "[REDACTED]"},
        )
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Unexpected error during refresh token validation: {err}",
            "error",
            exc=err,
            context={"refresh_token": "[REDACTED]"},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during refresh token validation.",
        )


def get_user_id_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> int:
    # Return the user ID associated with the token
    return get_token_user_id(refresh_token)


def get_and_return_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> str:
    # Return token
    return refresh_token


def check_scopes(
    access_token: Annotated[str, Depends(get_access_token)],
    security_scopes: SecurityScopes,
) -> None:
    # Get the scopes from the token
    scopes = get_token_scopes(access_token)

    try:
        # Use set operations to find missing scopes
        missing_scopes = set(security_scopes.scopes) - set(scopes)
        if missing_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Unauthorized Access - Missing permissions: {missing_scopes}",
                headers={
                    "WWW-Authenticate": f'Bearer scope="{security_scopes.scopes}"'
                },
            )
    except HTTPException as http_err:
        core_logger.print_to_log(
            f"Scope validation failed: {http_err}",
            "error",
            exc=http_err,
        )
        raise http_err
    except Exception as err:
        core_logger.print_to_log(
            f"Unexpected error during scope validation: {err}",
            "error",
            exc=err,
            context={"scopes": scopes, "required_scopes": security_scopes.scopes},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during scope validation.",
        )
