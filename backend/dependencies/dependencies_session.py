from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from dependencies import dependencies_database
from schemas import schema_access_tokens, schema_users

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def validate_token(token: str = Depends(oauth2_scheme), db: Session = Depends(dependencies_database.get_db)):
    # Validate the token expiration
    schema_access_tokens.validate_token_expiration(db, token)


def validate_token_and_get_authenticated_user_id(
    token: str = Depends(oauth2_scheme), db: Session = Depends(dependencies_database.get_db)
):
    # Validate the token expiration
    schema_access_tokens.validate_token_expiration(db, token)

    # Return the user ID associated with the token
    return schema_access_tokens.get_token_user_id(token)


def validate_token_and_validate_admin_access(
    token: str = Depends(oauth2_scheme), db: Session = Depends(dependencies_database.get_db)
):
    # Validate the token expiration
    schema_access_tokens.validate_token_expiration(db, token)

    # Check if the token has admin access
    schema_access_tokens.validate_token_admin_access(token)


def validate_token_and_if_user_id_equals_token_user_id_if_not_validate_admin_access(
    user_id: int | None,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(dependencies_database.get_db),
):
    # Validate the token expiration
    schema_access_tokens.validate_token_expiration(db, token)

    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Check if token id is different from user id. If yes, check if the token has admin access
    if user_id != schema_access_tokens.get_token_user_id(token):
        # Check if the token has admin access
        schema_access_tokens.validate_token_admin_access(token)


def validate_token_and_if_user_id_equals_token_user_attributtes_id_if_not_validate_admin_access(
    user_attributtes: schema_users.User,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(dependencies_database.get_db),
):
    validate_token_user_id_admin_access(db, token, user_attributtes.id)


def validate_token_and_if_user_id_equals_token_user_attributtes_password_id_if_not_validate_admin_access(
    user_attributtes: schema_users.UserEditPassword,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(dependencies_database.get_db),
):
    validate_token_user_id_admin_access(db, token, user_attributtes.id)


def validate_token_user_id_admin_access(db, token, user_id):
    # Validate the token expiration
    schema_access_tokens.validate_token_expiration(db, token)

    # Check if user_id higher than 0
    if not (int(user_id) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid user ID",
        )

    # Check if token id is different from user id. If yes, check if the token has admin access
    if user_id != schema_access_tokens.get_token_user_id(token):
        # Check if the token has admin access
        schema_access_tokens.validate_token_admin_access(token)