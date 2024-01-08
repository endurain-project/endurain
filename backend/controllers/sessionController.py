"""
Authentication and User Management Module

This module defines FastAPI routes and functions for user authentication, access token management,
and CRUD operations on user records. It integrates with a relational database using SQLAlchemy
and provides endpoints for handling user login, token validation, user data retrieval,
and logout functionality.

Endpoints:
- POST /token: Endpoint for user login to obtain an access token.
- GET /validate_token: Endpoint for validating the integrity and expiration of an access token.
- GET /users/me: Endpoint to retrieve user data based on the provided access token.
- DELETE /logout/{user_id}: Endpoint for user logout, revoking the associated access token.

Dependencies:
- OAuth2PasswordBearer: FastAPI security scheme for handling OAuth2 password bearer tokens.
- get_db_session: Dependency function to get a database session.
- create_error_response: Function to create a standardized error response.

Models:
- TokenBase: Base Pydantic model for token attributes.
- CreateTokenRequest: Pydantic model for creating token records.

Functions:
- authenticate_user: Function to authenticate a user and generate an access token.
- create_access_token: Function to create and store a new access token.
- remove_expired_tokens: Function to remove expired access tokens from the database.
- get_user_data: Function to retrieve user data based on the provided access token.
- validate_token: Function to validate the integrity and expiration of an access token.
- validate_admin_access: Function to validate if a user has admin access based on the token.

Logger:
- Logger named "myLogger" for logging errors and exceptions.
"""
# OS module for interacting with the operating system
import os

# Logging module for adding log statements to your code
import logging

# FastAPI framework imports
from fastapi import APIRouter, Depends

# Datetime module for working with date and time
from datetime import datetime, timedelta

# JOSE (JavaScript Object Signing and Encryption) library for JWT (JSON Web Tokens)
from jose import jwt, JWTError

# FastAPI security module for handling OAuth2 password bearer authentication
from fastapi.security import OAuth2PasswordBearer

# SQLAlchemy module for working with relational databases
from sqlalchemy.orm import Session

# Importing User and AccessToken models from the 'db' module
from db.db import User, AccessToken

# Importing UserResponse model from the 'controllers.userController' module
from controllers.userController import UserResponse

# Pydantic module for data validation and parsing
from pydantic import BaseModel

# Custom dependencies for dependency injection in FastAPI
from dependencies import get_db_session, create_error_response

from constants import ADMIN_ACCESS

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class TokenBase(BaseModel):
    """
    Base Pydantic model for representing token attributes.

    Attributes:
    - username (str): The username of the user.
    - password (str): The user password in hash format.
    - neverExpires (str): True or false value to set the token to expire.
    """
    username: str
    password: str
    neverExpires: bool

class CreateTokenRequest(TokenBase):
    """
    Pydantic model for creating token records.

    Inherits from TokenBase, which defines the base attributes for token.

    This class extends the TokenBase Pydantic model and is specifically tailored for
    creating new records.
    """
    pass


def decode_token(token: str):
    """
    Decode a JSON Web Token (JWT) and extract its payload.

    Parameters:
    - token (str): The JWT string to be decoded.

    Returns:
    - dict: A dictionary containing the decoded payload of the JWT.

    This function decodes a given JWT using the provided secret key and algorithm. It extracts and returns the payload
    of the JWT, which typically includes information such as user ID, access type, and expiration time.
    
    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    """
    try:
        payload = jwt.decode(
            token,
            os.environ.get("SECRET_KEY"),
            algorithms=[os.environ.get("ALGORITHM")],
        )
        return payload
    except JWTError:
        # Return an error response if the user is not authenticated
        return ("UNAUTHORIZED", "Unauthorized", 401)


def get_user_id_from_token(token: str):
    """
    Extract the user ID from a decoded JSON Web Token (JWT) payload.

    Parameters:
    - token (str): The decoded JWT string.

    Returns:
    - Union[int, Tuple[str, str, int]]: The user ID extracted from the JWT payload,
      or a tuple representing an error response if the token is invalid.

    This function retrieves the user ID from the decoded payload of a JWT. It is used for
    obtaining the user ID associated with a valid token during user authentication.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the extraction process.
    """
    try:
        return decode_token(token).get("id")
    except JWTError:
        # Return an error response if the user is not authenticated
        return ("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_id_from_token: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def get_exp_from_token(token: str = Depends(oauth2_scheme)):
    """
    Extract the expiration time from a decoded JSON Web Token (JWT) payload.

    Parameters:
    - token (str): The decoded JWT string.

    Returns:
    - Union[int, Tuple[str, str, int]]: The expiration time (UNIX timestamp) extracted
      from the JWT payload, or a tuple representing an error response if the token is invalid.

    This function retrieves the expiration time from the decoded payload of a JWT.
    It is used to check the validity and expiration status of an access token.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the extraction process.
    """
    try:
        return decode_token(token).get("exp")
    except JWTError:
        # Return an error response if the user is not authenticated
        return ("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_exp_from_token: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def get_access_type_from_token(token: str = Depends(oauth2_scheme)):
    """
    Extract the access type from a decoded JSON Web Token (JWT) payload.

    Parameters:
    - token (str): The decoded JWT string.

    Returns:
    - Union[int, Tuple[str, str, int]]: The access type extracted from the JWT payload,
      or a tuple representing an error response if the token is invalid.

    This function retrieves the access type from the decoded payload of a JWT.
    It is used to determine the level of access associated with a user's token.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the extraction process.
    """
    try:
        return decode_token(token).get("access_type")
    except JWTError:
        # Return an error response if the user is not authenticated
        return ("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_access_type_from_token: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


async def authenticate_user(
    username: str,
    password: str,
    neverExpires: bool,
    db_session: Session,
):
    """
    Authenticate a user and generate an access token.

    Parameters:
    - username (str): The username of the user attempting to authenticate.
    - password (str): The password of the user attempting to authenticate.
    - neverExpires (bool): Flag indicating whether the access token should never expire.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - Union[str, Tuple[str, str, int]]: The generated access token,
      or a tuple representing an error response if authentication fails.

    This function verifies the user's credentials, checks for an existing access token,
    and generates a new access token if necessary. The token's expiration is determined
    based on the 'neverExpires' flag.

    Raises:
    - Exception: If an unexpected error occurs during the authentication process.
    """
    try:
        # Use SQLAlchemy ORM to query the database
        user = (
            db_session.query(User)
            .filter(User.username == username, User.password == password)
            .first()
        )
        if not user:
            return create_error_response(
                "BAD_REQUEST", "Incorrect username or password", 400
            )

        # Check if there is an existing access token for the user
        access_token = (
            db_session.query(AccessToken).filter(AccessToken.user_id == user.id).first()
        )
        if access_token:
            return access_token.token

        # If there is no existing access token, create a new one
        access_token_expires = timedelta(
            minutes=int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))
        )
        access_token = await create_access_token(
            data={"id": user.id, "access_type": user.access_type},
            never_expire=neverExpires,
            db_session=db_session,
            expires_delta=access_token_expires,
        )

        return access_token

    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in authenticate_user: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


async def create_access_token(
    data: dict,
    never_expire: bool,
    db_session: Session,
    expires_delta: timedelta = None,
):
    """
    Create and store a new access token.

    Parameters:
    - data (dict): The payload data to be encoded in the access token.
    - never_expire (bool): Flag indicating whether the access token should never expire.
    - db_session (Session): SQLAlchemy database session.
    - expires_delta (timedelta, optional): Duration until the access token expires.

    Returns:
    - Union[str, Tuple[str, str, int]]: The generated access token,
      or a tuple representing an error response if token creation fails.

    This function creates a new access token by encoding the provided payload data.
    The token is then stored in the database, and the generated token string is returned.

    Raises:
    - Exception: If an unexpected error occurs during the token creation process.
    """
    try:
        to_encode = data.copy()
        if never_expire:
            expire = datetime.utcnow() + timedelta(days=90)
        elif expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode,
            os.environ.get("SECRET_KEY"),
            algorithm=os.environ.get("ALGORITHM"),
        )

        # Insert the access token into the database using SQLAlchemy
        access_token = AccessToken(
            token=encoded_jwt,
            user_id=data["id"],
            created_at=datetime.utcnow(),
            expires_at=expire,
        )

        db_session.add(access_token)
        db_session.commit()

        return encoded_jwt
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in create_access_token: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def remove_expired_tokens(db_session: Session):
    """
    Remove expired access tokens from the database.

    Parameters:
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - Union[None, Tuple[str, str, int]]: None on successful removal,
      or a tuple representing an error response if removal fails.

    This function deletes access tokens from the database that have exceeded their expiration time.
    It helps maintain the database's integrity by regularly purging expired access tokens.

    Raises:
    - Exception: If an unexpected error occurs during the removal process.
    """
    try:
        # Calculate the expiration time
        expiration_time = datetime.utcnow() - timedelta(
            minutes=int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))
        )

        # Delete expired access tokens using SQLAlchemy ORM
        rows_deleted = (
            db_session.query(AccessToken)
            .filter(AccessToken.created_at < expiration_time)
            .delete()
        )
        db_session.commit()

        logger.info(f"{rows_deleted} access tokens deleted from the database")
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in remove_expired_tokens: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def get_user_data(db_session: Session, token: str = Depends(oauth2_scheme)):
    """
    Retrieve user data based on the provided access token.

    Parameters:
    - db_session (Session): SQLAlchemy database session.
    - token (str): The access token for which user data is requested.

    Returns:
    - Union[dict, Tuple[str, str, int]]: A dictionary containing user data,
      or a tuple representing an error response if retrieval fails.

    This function fetches user data from the database using the provided access token.
    It validates the token, retrieves the associated user ID, and returns the user's details
    in a dictionary format.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the data retrieval process.
    """
    try:
        validate_token(db_session=db_session, token=token)

        user_id = get_user_id_from_token(token)
        if user_id is None:
            return create_error_response("UNAUTHORIZED", "Unauthorized", 401)

        # Retrieve the user details from the database using the user ID
        user = db_session.query(User).filter(User.id == user_id).first()

        if not user:
            return create_error_response("NOT_FOUND", "User not found", 404)

        if user.strava_token is None:
            is_strava_linked = 0
        else:
            is_strava_linked = 1

        # Map the user object to a dictionary that matches the UserResponse model
        user_data = {
            "id": user.id,
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "city": user.city,
            "birthdate": user.birthdate.strftime('%Y-%m-%d') if user.birthdate else None,
            "preferred_language": user.preferred_language,
            "gender": user.gender,
            "access_type": user.access_type,
            "photo_path": user.photo_path,
            "photo_path_aux": user.photo_path_aux,
            "is_active": user.is_active,
            "is_strava_linked": is_strava_linked,
        }

        return user_data
    except JWTError:
        # Return an error response if the user is not authenticated
        return ("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_data: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


def validate_token(db_session: Session, token: str):
    """
    Validate the integrity and expiration of an access token.

    Parameters:
    - db_session (Session): SQLAlchemy database session.
    - token (str): The access token to be validated.

    Returns:
    - Union[dict, Tuple[str, str, int]]: A dictionary with a success message if the token is valid,
      or a tuple representing an error response if validation fails.

    This function checks the integrity and expiration of the provided access token.
    It ensures that the token is associated with a valid user in the database and has not expired.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the validation process.
    """
    try:
        user_id = get_user_id_from_token(token)

        exp = get_exp_from_token(token)

        access_token = (
            db_session.query(AccessToken)
            .filter(AccessToken.user_id == user_id, AccessToken.token == token)
            .first()
        )

        if not access_token or datetime.utcnow() > datetime.fromtimestamp(exp):
            logger.info("Token expired, will force remove_expired_tokens to run")
            remove_expired_tokens(db_session=Session)
            raise JWTError("Token expired")
        else:
            return {"message": "Token is valid"}
    except JWTError as jwt_error:
        raise jwt_error
    except Exception as err:
        logger.error(f"Error in token validation: {err}", exc_info=True)
        raise JWTError("Token validation failed")


def validate_admin_access(token: str):
    """
    Validate if the user associated with the provided token has administrative access.

    Parameters:
    - token (str): The access token to be validated.

    Returns:
    - Union[None, Tuple[str, str, int]]: None if the user has admin access,
      or a tuple representing an error response if validation fails.

    This function checks if the user associated with the provided access token has administrative access.
    It verifies the access type stored in the token, allowing or denying access based on the user's privileges.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the validation process.
    """
    try:
        user_access_type = get_access_type_from_token(token)
        if user_access_type != ADMIN_ACCESS:
            return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except JWTError:
        raise JWTError("Invalid token")


@router.post("/token")
async def login_for_access_token(
    token: CreateTokenRequest, db_session: Session = Depends(get_db_session)
):
    """
    Endpoint for user login to obtain an access token.

    Parameters:
    - token (CreateTokenRequest): The request model containing username, password, and neverExpires flag.
    - db_session (Session, optional): SQLAlchemy database session. Obtained through dependency injection.

    Returns:
    - Union[dict, Tuple[str, str, int]]: A dictionary containing the access token if login is successful,
      or a tuple representing an error response if login fails.

    This endpoint handles user authentication by verifying the provided credentials.
    If successful, it generates an access token and returns it to the user.

    Raises:
    - Exception: If an unexpected error occurs during the authentication process.
    """
    access_token = await authenticate_user(
        token.username, token.password, token.neverExpires, db_session
    )
    if not access_token:
        return create_error_response(
            "BAD_REQUEST", "Unable to retrieve access token", 400
        )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/validate_token")
async def check_validate_token(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Endpoint for validating the integrity and expiration of an access token.

    Parameters:
    - token (str): The access token to be validated.
    - db_session (Session, optional): SQLAlchemy database session. Obtained through dependency injection.

    Returns:
    - Union[dict, Tuple[str, str, int]]: A dictionary with a success message if the token is valid,
      or a tuple representing an error response if validation fails.

    This endpoint checks the integrity and expiration of the provided access token.
    If the token is valid, it returns a success message; otherwise, it returns an error response.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the validation process.
    """
    try:
        return validate_token(db_session, token)
    except JWTError:
        # Return an error response if the user is not authenticated
        return ("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_data: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/users/me", response_model=UserResponse)
async def read_users_me(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Endpoint to retrieve user data based on the provided access token.

    Parameters:
    - token (str): The access token used to identify the user.
    - db_session (Session, optional): SQLAlchemy database session. Obtained through dependency injection.

    Returns:
    - Union[dict, Tuple[str, str, int]]: A dictionary containing user data,
      or a tuple representing an error response if retrieval fails.

    This endpoint fetches and returns the user's data based on the provided access token.
    It validates the token, retrieves the associated user ID, and returns the user's details
    in a format consistent with the UserResponse Pydantic model.

    Raises:
    - JWTError: If there is an issue with JWT decoding or the token is invalid.
    - Exception: If an unexpected error occurs during the data retrieval process.
    """
    return get_user_data(db_session, token)


@router.delete("/logout/{user_id}")
async def logout(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Endpoint for user logout, revoking the associated access token.

    Parameters:
    - user_id (int): The user ID for which logout is requested.
    - token (str): The access token used to identify the user.
    - db_session (Session, optional): SQLAlchemy database session. Obtained through dependency injection.

    Returns:
    - Union[dict, Tuple[str, str, int]]: A dictionary with a success message if logout is successful,
      or a tuple representing an error response if logout fails.

    This endpoint revokes the access token associated with the provided user ID, effectively logging the user out.
    If the token is found and successfully revoked, it returns a success message; otherwise, it returns an error response.

    Raises:
    - Exception: If an unexpected error occurs during the logout process.
    """
    try:
        access_token = (
            db_session.query(AccessToken)
            .filter(AccessToken.user_id == user_id, AccessToken.token == token)
            .first()
        )
        if access_token:
            db_session.delete(access_token)
            db_session.commit()
            return {"message": "Logged out successfully"}
        else:
            return create_error_response("NOT_FOUND", "Token not found", 404)

    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in logout: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )
