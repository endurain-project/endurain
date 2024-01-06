"""
API Router for managing user followers information.

This module defines FastAPI routes for handling user follower relationships.
It includes endpoints for retrieving follower information, creating, accepting,
and deleting follower relationships. The routes handle user authentication,
database interactions using SQLAlchemy, and provide JSON responses with appropriate metadata.

Endpoints:
- GET /followers/user/{user_id}/targetUser/{target_user_id}: Retrieve specific follower relationship details.
- GET /followers/user/{user_id}/followers/count/all: Retrieve the total number of followers for a user.
- GET /followers/user/{user_id}/followers/count: Retrieve the count of accepted followers for a user.
- GET /followers/user/{user_id}/followers/all: Retrieve all followers for a user.
- GET /followers/user/{user_id}/following/count/all: Retrieve the total number of users a user is following.
- GET /followers/user/{user_id}/following/count: Retrieve the count of accepted users a user is following.
- GET /followers/user/{user_id}/following/all: Retrieve all users a user is following.
- PUT /followers/accept/user/{user_id}/targetUser/{target_user_id}: Accept a follow request.
- POST /followers/create/user/{user_id}/targetUser/{target_user_id}: Create a new follower relationship.
- DELETE /followers/delete/user/{user_id}/targetUser/{target_user_id}: Delete a follower relationship.

Dependencies:
- OAuth2PasswordBearer: FastAPI security scheme for handling OAuth2 password bearer tokens.
- get_db_session: Dependency function to get a database session.
- create_error_response: Function to create a standardized error response.

Models:
- Follower: SQLAlchemy model for the follower relationship.
- JSONResponse: FastAPI response model for JSON content.

Functions:
- validate_token: Function to validate user access tokens.
- create_error_response: Function to create a standardized error response.

Logger:
- Logger named "myLogger" for logging errors and exceptions.

"""
import logging
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from . import sessionController
from jose import JWTError
from fastapi.responses import JSONResponse
from db.db import (
    Follower,
)
from dependencies import get_db_session, create_error_response
from sqlalchemy.orm import Session

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Define an HTTP GET route to retrieve the number of users
@router.get("/followers/user/{user_id}/targetUser/{target_user_id}")
async def read_followers_user_specific_user(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve specific follower relationship details.

    Parameters:
    - user_id (int): The ID of the user whose followers are being queried.
    - target_user_id (int): The ID of the target user in the relationship.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and follower relationship details.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query the specific follower record
        follower = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == user_id)
                & (Follower.following_id == target_user_id)
            )
            .first()
        )

        if follower:
            # Include metadata in the response
            metadata = {"total_records": 1}

            # User follows target_user_id or vice versa
            response_data = {
                "follower_id": user_id,
                "following_id": target_user_id,
                "is_accepted": follower.is_accepted,
            }

            # Return the queried values using JSONResponse
            return JSONResponse(
                content={"metadata": metadata, "content": response_data}
            )

        # Users are not following each other
        return create_error_response("NOT_FOUND", "Users are not following each other.", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_followers_user_specific_user: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/followers/user/{user_id}/followers/count/all")
async def get_user_follower_count_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the total number of followers for a user.

    Parameters:
    - user_id (int): The ID of the user whose follower count is being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the total follower count.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query the specific follower record and retrieve count
        follower_count = (
            db_session.query(Follower).filter(Follower.follower_id == user_id).count()
        )

        # Include metadata in the response
        metadata = {"total_records": 1}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": follower_count}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_follower_count_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )



@router.get("/followers/user/{user_id}/followers/count")
async def get_user_follower_count(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the count of accepted followers for a user.

    Parameters:
    - user_id (int): The ID of the user whose accepted follower count is being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the count of accepted followers.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the count of entries where user_id is equal to Follower.follower_id
        follower_count = (
            db_session.query(Follower)
            .filter((Follower.follower_id == user_id) & (Follower.is_accepted == True))
            .count()
        )

        # Include metadata in the response
        metadata = {"total_records": 1}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": follower_count}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_follower_count: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/followers/user/{user_id}/followers/all")
async def get_user_follower_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve all followers for a user.

    Parameters:
    - user_id (int): The ID of the user whose followers are being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and a list of follower details.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the entries where both conditions are met
        followers = (
            db_session.query(Follower).filter(Follower.following_id == user_id).all()
        )

        # Convert the query result to a list of dictionaries
        followers_list = [
            {"follower_id": follower.follower_id, "is_accepted": follower.is_accepted}
            for follower in followers
        ]

        # Include metadata in the response
        metadata = {"total_records": len(followers_list)}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": followers_list}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_follower_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/followers/user/{user_id}/following/count/all")
async def get_user_following_count_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the total number of users a user is following.

    Parameters:
    - user_id (int): The ID of the user whose following count is being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the total following count.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query the specific follower record and retrieve count
        following_count = (
            db_session.query(Follower).filter(Follower.following_id == user_id).count()
        )

        # Include metadata in the response
        metadata = {"total_records": 1}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": following_count}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_following_count_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/followers/user/{user_id}/following/count")
async def get_user_following_count(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the count of accepted users a user is following.

    Parameters:
    - user_id (int): The ID of the user whose accepted following count is being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and the count of accepted following relationships.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the count of entries where user_id is equal to Follower.follower_id
        following_count = (
            db_session.query(Follower)
            .filter((Follower.following_id == user_id) & (Follower.is_accepted == True))
            .count()
        )

        # Include metadata in the response
        metadata = {"total_records": 1}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": following_count}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_following_count: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/followers/user/{user_id}/following/all")
async def get_user_following_all(
    user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve all users a user is following.

    Parameters:
    - user_id (int): The ID of the user whose following relationships are being queried.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and a list of following details.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query for the entries where both conditions are met
        followings = (
            db_session.query(Follower).filter(Follower.follower_id == user_id).all()
        )

        # Convert the query result to a list of dictionaries
        following_list = [
            {
                "following_id": following.following_id,
                "is_accepted": following.is_accepted,
            }
            for following in followings
        ]

        # Include metadata in the response
        metadata = {"total_records": len(following_list)}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": following_list}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in get_user_following_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.put("/followers/accept/user/{user_id}/targetUser/{target_user_id}")
async def accept_follow(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Accept a follow request.

    Parameters:
    - user_id (int): The ID of the user who will accept the follow request.
    - target_user_id (int): The ID of the user who sent the follow request.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing details of the accepted follower relationship.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Check if the follow relationship exists and is not accepted yet
        follow_request = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == target_user_id)
                & (Follower.following_id == user_id)
                & (Follower.is_accepted == False)
            )
            .first()
        )

        if follow_request:
            # Accept the follow request by changing the "is_accepted" column to True
            follow_request.is_accepted = True
            db_session.commit()

            # Return success response
            response_data = {
                "follower_id": target_user_id,
                "following_id": user_id,
                "is_accepted": True,
            }
            return JSONResponse(content=response_data, status_code=200)
        else:
            # Follow request does not exist or has already been accepted
            return create_error_response("BAD_REQUEST", "Invalid follow request.", 400)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in accept_follow: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.post("/followers/create/user/{user_id}/targetUser/{target_user_id}")
async def create_follow(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Create a new follower relationship.

    Parameters:
    - user_id (int): The ID of the user who will follow another user.
    - target_user_id (int): The ID of the user to be followed.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing details of the newly created follower relationship.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Check if the follow relationship already exists
        existing_follow = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == user_id)
                & (Follower.following_id == target_user_id)
            )
            .first()
        )

        if existing_follow:
            # Follow relationship already exists
            return create_error_response("BAD_REQUEST", "Follow relationship already exists.", 400)

        # Create a new follow relationship
        new_follow = Follower(
            follower_id=user_id, following_id=target_user_id, is_accepted=False
        )

        # Add the new follow relationship to the database
        db_session.add(new_follow)
        db_session.commit()

        # Return success response
        response_data = {
            "follower_id": user_id,
            "following_id": target_user_id,
            "is_accepted": False,
        }
        return JSONResponse(content=response_data, status_code=201)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in create_follow: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.delete("/followers/delete/user/{user_id}/targetUser/{target_user_id}")
async def delete_follow(
    user_id: int,
    target_user_id: int,
    token: str = Depends(oauth2_scheme),
    db_session: Session = Depends(get_db_session),
):
    """
    Delete a follower relationship.

    Parameters:
    - user_id (int): The ID of the user who will unfollow another user.
    - target_user_id (int): The ID of the user to be unfollowed.
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response indicating the success of the unfollow operation.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    try:
        # Validate the user's access token using the oauth2_scheme
        sessionController.validate_token(db_session, token)

        # Query and delete the specific follower record
        follower = (
            db_session.query(Follower)
            .filter(
                (Follower.follower_id == user_id)
                & (Follower.following_id == target_user_id)
            )
            .first()
        )

        if follower:
            # Delete the follower record
            db_session.delete(follower)
            db_session.commit()

            # Respond with a success message
            return JSONResponse(
                content={"detail": "Follower record deleted successfully."},
                status_code=200,
            )

        # Follower record not found
        return create_error_response("NOT_FOUND", "Follower record not found.", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in delete_follow: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )
