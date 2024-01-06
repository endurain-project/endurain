"""
API Router for managing user information.

This module defines FastAPI routes for performing CRUD operations on user records.
It includes endpoints for retrieving, creating, updating, and deleting user records.
The routes handle user authentication, database interactions using SQLAlchemy,
and provide JSON responses with appropriate metadata.

Endpoints:
- GET /users/all: Retrieve all users.
- GET /users/number: Retrieve the total number of users.
- GET /users/all/pagenumber/{pageNumber}/numRecords/{numRecords}: Retrieve users with pagination.
- GET /users/username/{username}: Retrieve users by username.
- GET /users/id/{user_id}: Retrieve users by user ID.
- GET /users/{username}/id: Retrieve user ID by username.
- GET /users/{user_id}/photo_path: Retrieve user photo path by user ID.
- GET /users/{user_id}/photo_path_aux: Retrieve user photo path aux by user ID.
- POST /users/create: Create a new user.
- PUT /users/{user_id}/edit: Edit an existing user.
- PUT /users/{user_id}/delete-photo: Delete a user's photo.
- DELETE /users/{user_id}/delete: Delete a user.

Dependencies:
- OAuth2PasswordBearer: FastAPI security scheme for handling OAuth2 password bearer tokens.
- get_db_session: Dependency function to get a database session.
- create_error_response: Function to create a standardized error response.

Models:
- UserBase: Base Pydantic model for user attributes.
- UserCreateRequest: Pydantic model for creating user records.
- UserEditRequest: Pydantic model for editing user records.
- UserResponse: Pydantic model for user responses.

Functions:
- user_record_to_dict: Convert User SQLAlchemy objects to dictionaries.

Logger:
- Logger named "myLogger" for logging errors and exceptions.
"""
import logging
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import List, Optional
from jose import JWTError
from fastapi.responses import JSONResponse
from datetime import date
from . import sessionController
from sqlalchemy.orm import Session
from db.db import (
    User,
    Gear,
)
from urllib.parse import unquote
from dependencies import get_db_session, create_error_response

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class UserBase(BaseModel):
    """
    Base Pydantic model for representing user attributes.

    Attributes:
    - name (str): The name of the user.
    - username (str): The username of the user.
    - email (str): The email address of the user.
    - preferred_language (str): The preferred language of the user.
    - city (str, optional): The city where the user resides.
    - birthdate (str, optional): The birthdate of the user.
    - gender (int): The gender of the user.
    - access_type (int): The access type of the user.
    - photo_path (str, optional): The path to the user's main photo.
    - photo_path_aux (str, optional): The path to the user's auxiliary photo.
    - is_active (int): The status indicating whether the user is active.
    """

    name: str
    username: str
    email: str
    preferred_language: str
    city: Optional[str]
    birthdate: Optional[str]
    gender: int
    access_type: int
    photo_path: Optional[str]
    photo_path_aux: Optional[str]
    is_active: int

class UserCreateRequest(UserBase):
    """
    Pydantic model for creating user records.

    Inherits from UserBase, which defines the base attributes for user.

    This class extends the UserBase Pydantic model and is designed for creating 
    new user records. Includes an additional attribute 'password'
    to idefine user password.

    """
    password: str

class UserEditRequest(UserBase):
    """
    Pydantic model for editing user records.

    Inherits from UserBase, which defines the base attributes for user.

    This class extends the UserBase Pydantic model and is specifically tailored for
    editing existing user records.
    """
    pass

class UserResponse(UserBase):
    """
    Pydantic model for representing user responses.

    Inherits from UserBase, which defines the base attributes for a user.

    This class extends the UserBase Pydantic model and is designed for representing
    user responses. It includes an additional attribute 'id' to represent the user's ID.

    Attributes:
    - id (int): The unique identifier for the user.
    - is_strava_linked (int, optional): Indicator for whether the user is linked to Strava.
    """

    id: int
    is_strava_linked: Optional[int]

# Define a function to convert User SQLAlchemy objects to dictionaries
def user_record_to_dict(record: User) -> dict:
    """
    Convert User SQLAlchemy objects to dictionaries.

    Parameters:
    - record (User): The User SQLAlchemy object to convert.

    Returns:
    - dict: A dictionary representation of the User object.

    This function is used to convert an SQLAlchemy User object into a dictionary format for easier serialization and response handling.
    """
    return {
        "id": record.id,
        "name": record.name,
        "username": record.username,
        "email": record.email,
        "city": record.city,
        "birthdate": record.birthdate,
        "preferred_language": record.preferred_language,
        "gender": record.gender,
        "access_type": record.access_type,
        "photo_path": record.photo_path,
        "photo_path_aux": record.photo_path_aux,
        "is_active": record.is_active,
        "strava_state": record.strava_state,
        "strava_token": record.strava_token,
        "strava_refresh_token": record.strava_refresh_token,
        "strava_token_expires_at": record.strava_token_expires_at,
    }


# Define an HTTP GET route to retrieve all users
@router.get("/users/all", response_model=list[dict])
async def read_users_all(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Retrieve all user records.

    Parameters:
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and user records.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Query all users from the database
        user_records = db_session.query(User).all()

        # Use the user_record_to_dict function to convert SQLAlchemy objects to dictionaries
        user_records_dict = [user_record_to_dict(record) for record in user_records]

        # Include metadata in the response
        metadata = {"total_records": len(user_records)}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": user_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP GET route to retrieve the number of users
@router.get("/users/number")
async def read_users_number(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Retrieve the total number of user records.

    Parameters:
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the total number of user records.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Count the number of users in the database
        user_count = db_session.query(User).count()

        # Include metadata in the response
        metadata = {"total_records": 1}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": user_count})

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_number: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP GET route to retrieve user records with pagination
@router.get(
    "/users/all/pagenumber/{pageNumber}/numRecords/{numRecords}",
    response_model=List[dict],
)
async def read_users_all_pagination(
    pageNumber: int,
    numRecords: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user records with pagination.

    Parameters:
    - pageNumber (int): The page number for pagination.
    - numRecords (int): The number of records to retrieve per page.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and user records for the specified page.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Use SQLAlchemy to query the user records with pagination
        user_records = (
            db_session.query(User)
            .order_by(User.name.asc())
            .offset((pageNumber - 1) * numRecords)
            .limit(numRecords)
            .all()
        )

        # Use the user_record_to_dict function to convert SQLAlchemy objects to dictionaries
        user_records_dict = [user_record_to_dict(record) for record in user_records]

        # Include metadata in the response
        metadata = {"total_records": len(user_records)}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": user_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_all_pagination: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP GET route to retrieve user records by username
@router.get("/users/username/{username}", response_model=List[dict])
async def read_users_username(
    username: str,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user records by username.

    Parameters:
    - username (str): The username to search for.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and user records matching the username.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Define a search term
        partial_username = unquote(username).replace("+", " ")

        # Use SQLAlchemy to query the user records by username
        user_records = (
            db_session.query(User)
            .filter(User.username.like(f"%{partial_username}%"))
            .all()
        )

        # Use the user_record_to_dict function to convert SQLAlchemy objects to dictionaries
        user_records_dict = [user_record_to_dict(record) for record in user_records]

        # Include metadata in the response
        metadata = {"total_records": len(user_records)}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": user_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_username: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP GET route to retrieve user records by user ID
@router.get("/users/id/{user_id}", response_model=List[dict])
async def read_users_id(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user records by user ID.

    Parameters:
    - user_id (int): The ID of the user to retrieve.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and user records matching the user ID.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Use SQLAlchemy to query the user records by user ID
        user_records = db_session.query(User).filter(User.id == user_id).all()

        # Use the user_record_to_dict function to convert SQLAlchemy objects to dictionaries
        user_records_dict = [user_record_to_dict(record) for record in user_records]

        # Include metadata in the response
        metadata = {"total_records": len(user_records)}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": user_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_id: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP GET route to retrieve user ID by username
@router.get("/users/{username}/id")
async def read_users_username_id(
    username: str,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user ID by username.

    Parameters:
    - username (str): The username to search for.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the user ID matching the username.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Use SQLAlchemy to query the user ID by username
        user_id = (
            db_session.query(User.id)
            .filter(User.username == unquote(username).replace("+", " "))
            .first()
        )

        # Include metadata in the response
        metadata = {"total_records": 1}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": {"id": user_id}}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_username_id: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP GET route to retrieve user photos by user ID
@router.get("/users/{user_id}/photo_path")
async def read_users_id_photo_path(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user photo path by user ID.

    Parameters:
    - user_id (int): The ID of the user to retrieve the photo path for.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the user's photo path.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Use SQLAlchemy to query the user's photo path by user ID
        user = db_session.query(User.photo_path).filter(User.id == user_id).first()

        if user:
            # Include metadata in the response
            metadata = {"total_records": 1}

            # Return the queried values using JSONResponse
            return JSONResponse(
                content={"metadata": metadata, "content": {"photo_path": user.photo_path}}
            )
        else:
            # Handle the case where the user was not found or doesn't have a photo path
            return create_error_response("NOT_FOUND", "User not found or no photo path available", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_id_photo_path: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP GET route to retrieve user photos aux by user ID
@router.get("/users/{user_id}/photo_path_aux")
async def read_users_id_photo_path_aux(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user photo path aux by user ID.

    Parameters:
    - user_id (int): The ID of the user to retrieve the auxiliary photo path for.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the user's auxiliary photo path.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Use SQLAlchemy to query the user's photo path by user ID
        user = db_session.query(User.photo_path_aux).filter(User.id == user_id).first()

        if user:
            # Include metadata in the response
            metadata = {"total_records": 1}

            # Return the queried values using JSONResponse
            return JSONResponse(
                content={"metadata": metadata, "content": {"photo_path_aux": user.photo_path_aux}}
            )
        else:
            # Handle the case where the user was not found or doesn't have a photo path aux
            return create_error_response("NOT_FOUND", "User not found or no photo path aux available", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_users_id_photo_path_aux: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP POST route to create a new user
@router.post("/users/create")
async def create_user(
    user: UserCreateRequest,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Create a new user.

    Parameters:
    - user (UserCreateRequest): Pydantic model containing the user information for creation.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of the user creation.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Create a new User instance using SQLAlchemy's ORM
        new_user = User(
            name=user.name,
            username=user.username,
            email=user.email,
            password=user.password,
            preferred_language=user.preferred_language,
            city=user.city,
            birthdate=user.birthdate,
            gender=user.gender,
            access_type=user.access_type,
            photo_path=user.photo_path,
            photo_path_aux=user.photo_path_aux,
            is_active=user.is_active,
        )

        # Add the new user to the database
        db_session.add(new_user)
        db_session.commit()

        # Return a JSONResponse indicating the success of the user creation
        return JSONResponse(
            content={"message": "User created successfully"}, status_code=201
        )
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in create_user: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP PUT route to edit a user's information
@router.put("/users/{user_id}/edit")
async def edit_user(
    user_id: int,
    user_attributtes: UserEditRequest,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Edit an existing user's information.

    Parameters:
    - user_id (int): The ID of the user to edit.
    - user_attributes (UserEditRequest): Pydantic model containing the user information for editing.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of the user edit.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Query the database to find the user by their ID
        user = db_session.query(User).filter(User.id == user_id).first()

        # Check if the user with the given ID exists
        if not user:
            # Return an error response if the user record is not found
            return create_error_response("NOT_FOUND", "User not found", 404)

        # Update user information if provided in the form data
        if user_attributtes.name is not None:
            user.name = user_attributtes.name
        if user_attributtes.username is not None:
            user.username = user_attributtes.username
        if user_attributtes.email is not None:
            user.email = user_attributtes.email
        if user_attributtes.preferred_language is not None:
            user.preferred_language = user_attributtes.preferred_language
        if user_attributtes.city is not None:
            user.city = user_attributtes.city
        if user_attributtes.birthdate is not None:
            user.birthdate = user_attributtes.birthdate
        if user_attributtes.gender is not None:
            user.gender = user_attributtes.gender
        if user_attributtes.access_type is not None:
            user.access_type = user_attributtes.access_type
        if user_attributtes.photo_path is not None:
            user.photo_path = user_attributtes.photo_path
        if user_attributtes.photo_path_aux is not None:
            user.photo_path_aux = user_attributtes.photo_path_aux
        if user_attributtes.is_active is not None:
            user.is_active = user_attributtes.is_active

        # Commit the changes to the database
        db_session.commit()

        # Return a JSONResponse indicating the success of the user edit
        return JSONResponse(
            content={"message": "User edited successfully"}, status_code=200
        )
        
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in edit_user: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP PUT route to delete a user's photo
@router.put("/users/{user_id}/delete-photo")
async def delete_user_photo(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Delete a user's photo.

    Parameters:
    - user_id (int): The ID of the user to delete the photo for.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of the photo deletion.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        # Query the database to find the user by their ID
        user = db_session.query(User).filter(User.id == user_id).first()

        # Check if the user with the given ID exists
        if not user:
            # Return an error response if the user record is not found
            return create_error_response("NOT_FOUND", "User not found", 404)

        # Set the user's photo paths to None to delete the photo
        user.photo_path = None
        user.photo_path_aux = None

        # Commit the changes to the database
        db_session.commit()

        # Return a JSONResponse indicating the success of the user edit
        return JSONResponse(
            content={"message": f"Photo for user {user_id} has been deleted"}, status_code=200
        )
        
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in delete_user_photo: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Define an HTTP DELETE route to delete a user
@router.delete("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Delete a user.

    Parameters:
    - user_id (int): The ID of the user to delete.
    - token (str): The access token for user authentication.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of the user deletion.

    Raises:
    - JWTError: If the user's access token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Validate that the user has admin access
        sessionController.validate_admin_access(token)

        user = db_session.query(User).filter(User.id == user_id).first()

        # Check if the user with the given ID exists
        if not user:
            # Return an error response if the user record is not found
            return create_error_response("NOT_FOUND", "User not found", 404)

        # Check for existing dependencies if needed (e.g., related systems)
        count_gear = db_session.query(Gear).filter(Gear.user_id == user_id).count()
        if count_gear > 0:
            # Return an error response if the user has gear created
            return create_error_response("CONFLIT", "Cannot delete user due to existing dependencies", 409)
        # Delete the user from the database
        db_session.delete(user)
        db_session.commit()

        # Return a JSONResponse indicating the success of the user edit
        return JSONResponse(
            content={"message": f"User {user_id} has been deleted"}, status_code=200
        )
        
    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in delete_user: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )
