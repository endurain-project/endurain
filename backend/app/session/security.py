from typing import Annotated, Union
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    OAuth2PasswordBearer,
    SecurityScopes,
    APIKeyHeader,
    APIKeyCookie,
)

import session.constants as session_constants
import session.token_manager as session_token_manager

import core.logger as core_logger

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="token",
    scopes=session_constants.SCOPE_DICT,
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
    if client_type == "mobile":
        return noncookie_token
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
    token_manager: Annotated[
        session_token_manager.TokenManager,
        Depends(session_token_manager.get_token_manager),
    ],
) -> None:
    try:
        # Validate the token expiration
        token_manager.validate_token_expiration(access_token)
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
        ) from err


def get_user_id_from_access_token(
    access_token: Annotated[str, Depends(get_access_token)],
    token_manager: Annotated[
        session_token_manager.TokenManager,
        Depends(session_token_manager.get_token_manager),
    ],
) -> int:
    # Return the user ID associated with the token
    return token_manager.get_token_user_id(access_token)


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
    token_manager: Annotated[
        session_token_manager.TokenManager,
        Depends(session_token_manager.get_token_manager),
    ],
) -> None:
    try:
        # Validate the token expiration
        token_manager.validate_token_expiration(refresh_token)
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
        ) from err


def get_user_id_from_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
    token_manager: Annotated[
        session_token_manager.TokenManager,
        Depends(session_token_manager.get_token_manager),
    ],
) -> int:
    # Return the user ID associated with the token
    return token_manager.get_token_user_id(refresh_token)


def get_and_return_refresh_token(
    refresh_token: Annotated[str, Depends(get_refresh_token)],
) -> str:
    # Return token
    return refresh_token


def check_scope(
    access_token: Annotated[str, Depends(get_access_token)],
    token_manager: Annotated[
        session_token_manager.TokenManager,
        Depends(session_token_manager.get_token_manager),
    ],
    security_scopes: SecurityScopes,
) -> None:
    # Get the scope from the token
    scope = token_manager.get_token_scopes(access_token)

    try:
        # Use set operations to find missing scope
        missing_scopes = set(security_scopes.scopes) - set(scope)
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
            context={"scope": scope, "required_scope": security_scopes.scopes},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during scope validation.",
        ) from err
