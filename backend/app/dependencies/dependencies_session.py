from fastapi import Depends, HTTPException, status, Request, Security
from fastapi.security import OAuth2PasswordBearer, SecurityScopes
from sqlalchemy.orm import Session

from typing import Annotated

from session import dependencies_security

import users.schema as users_schema

import database

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


### Dependencies for access token validation


def validate_access_token(request: Request):
    # Extract the access token from the cookies
    access_token = request.cookies.get("endurain_access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate the token expiration
    dependencies_security.validate_token_expiration(access_token)


def validate_token_and_return_access_token(request: Request):
    # Extract the access token from the cookies
    access_token = request.cookies.get("endurain_access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate the token expiration
    dependencies_security.validate_token_expiration(access_token)

    # Return token
    return access_token


def validate_access_token_and_get_authenticated_user_id(
    access_token: Annotated[str, Depends(validate_token_and_return_access_token)],
):
    # Return the user ID associated with the token
    return dependencies_security.get_token_user_id(access_token)


def validate_access_token_and_validate_admin_access(
    access_token: Annotated[str, Depends(validate_token_and_return_access_token)],
):
    # Check if the token has admin access
    dependencies_security.validate_token_admin_access(access_token)


### Dependencies for refresh token validation


def validate_token_and_return_refresh_token(request: Request):
    # Extract the refresh token from the cookies
    refresh_token = request.cookies.get("endurain_refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Refresh token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate the token expiration
    dependencies_security.validate_token_expiration(refresh_token)

    # Return token
    return refresh_token


def validate_refresh_token_and_get_authenticated_user_id(
    refresh_token: Annotated[str, Depends(validate_token_and_return_refresh_token)]
):
    # Return the user ID associated with the token
    return dependencies_security.get_token_user_id(refresh_token)


def validate_token_and_validate_admin_access(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
):
    # Validate the token expiration
    dependencies_security.validate_token_expiration(token)

    # Check if the token has admin access
    dependencies_security.validate_token_admin_access(token)


def validate_token_and_if_user_id_equals_token_user_id_if_not_validate_admin_access(
    user_id: int | None,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
):
    # Validate the token expiration
    dependencies_security.validate_token_expiration(token)

    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Check if token id is different from user id. If yes, check if the token has admin access
    if user_id != dependencies_security.get_token_user_id(token):
        # Check if the token has admin access
        dependencies_security.validate_token_admin_access(token)


def validate_token_and_if_user_id_equals_token_user_attributtes_id_if_not_validate_admin_access(
    user_attributtes: users_schema.User,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
):
    validate_token_user_id_admin_access(db, token, user_attributtes.id)


def validate_token_and_if_user_id_equals_token_user_attributtes_password_id_if_not_validate_admin_access(
    user_attributtes: users_schema.UserEditPassword,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(database.get_db),
):
    validate_token_user_id_admin_access(db, token, user_attributtes.id)


def validate_token_user_id_admin_access(db, token, user_id):
    # Validate the token expiration
    dependencies_security.validate_token_expiration(token)

    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Check if token id is different from user id. If yes, check if the token has admin access
    if user_id != dependencies_security.get_token_user_id(token):
        # Check if the token has admin access
        dependencies_security.validate_token_admin_access(token)


def check_scopes(
    security_scopes: SecurityScopes,
    # scopes: Annotated[list[str], Depends(dependencies_security.get_token_scopes)],
    access_token: Annotated[str, Depends(validate_token_and_return_access_token)],
):
    # Get the scopes from the token
    scopes = dependencies_security.get_token_scopes(access_token)

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
