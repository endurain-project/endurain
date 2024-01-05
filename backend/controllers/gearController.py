"""
API Router for managing user gear information.

This module defines FastAPI routes for performing CRUD operations on user gear records.
It includes endpoints for retrieving, creating, updating, and deleting gear records.
The routes handle user authentication, database interactions using SQLAlchemy,
and provide JSON responses with appropriate metadata.

Endpoints:
- GET /gear/all: Retrieve all user gear records.
- GET /gear/all/{gear_type}: Retrieve user gear records filtered by gear type.
- GET /gear/number: Retrieve the total number of user gear records.
- GET /gear/all/pagenumber/{pageNumber}/numRecords/{numRecords}: Retrieve user gear records with pagination.
- GET /gear/{nickname}/gearfromnickname: Retrieve user gear records by nickname.
- GET /gear/{id}/gearfromid: Retrieve user gear records by ID.
- POST /gear/create: Create a new user gear record.
- PUT /gear/{gear_id}/edit: Edit an existing user gear record.
- DELETE /gear/{gear_id}/delete: Delete an existing user gear record.

Dependencies:
- OAuth2PasswordBearer: FastAPI security scheme for handling OAuth2 password bearer tokens.
- get_db_session: Dependency function to get a database session.
- create_error_response: Function to create a standardized error response.
- get_current_user: Dependency function to get the current authenticated user.

Models:
- GearBase: Base Pydantic model for gear attributes.
- GearCreateRequest: Pydantic model for creating gear records.
- GearEditRequest: Pydantic model for editing gear records.

Functions:
- gear_record_to_dict: Convert Gear SQLAlchemy objects to dictionaries.

Logger:
- Logger named "myLogger" for logging errors and exceptions.

"""
import logging
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from db.db import Gear
from jose import JWTError
from urllib.parse import unquote
from pydantic import BaseModel
from dependencies import get_db_session, create_error_response, get_current_user
from fastapi.responses import JSONResponse

# Define the API router
router = APIRouter()

# Define a loggger created on main.py
logger = logging.getLogger("myLogger")

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class GearBase(BaseModel):
    """
    Base Pydantic model for representing gear attributes.

    Attributes:
    - brand (str, optional): The brand of the gear.
    - model (str, optional): The model of the gear.
    - nickname (str): The nickname of the gear.
    - gear_type (int): The type of gear.
    - date (str): The creation date of the gear.
    """

    brand: Optional[str]
    model: Optional[str]
    nickname: str
    gear_type: int
    date: str


class GearCreateRequest(GearBase):
    """
    Pydantic model for creating gear records.

    Inherits from GearBase, which defines the base attributes for gear.

    This class extends the GearBase Pydantic model and is specifically tailored for
    creating new gear records.
    """

    pass


class GearEditRequest(GearBase):
    """
    Pydantic model for editing gear records.

    Inherits from GearBase, which defines the base attributes for gear.

    This class extends the GearBase Pydantic model and is designed for editing existing
    gear records. Includes an additional attribute 'is_active'
    to indicate whether the gear is active or not.

    """

    is_active: int


# Define a function to convert Gear SQLAlchemy objects to dictionaries
def gear_record_to_dict(record: Gear) -> dict:
    """
    Convert Gear SQLAlchemy objects to dictionaries.

    Parameters:
    - record (Gear): The Gear SQLAlchemy object to convert.

    Returns:
    - dict: A dictionary representation of the Gear object.

    This function is used to convert an SQLAlchemy Gear object into a dictionary format for easier serialization and response handling.
    """
    return {
        "id": record.id,
        "brand": record.brand,
        "model": record.model,
        "nickname": record.nickname,
        "gear_type": record.gear_type,
        "user_id": record.user_id,
        "created_at": record.created_at.strftime("%Y-%m-%dT%H:%M:%S"),
        "is_active": record.is_active,
    }


@router.get("/gear/all", response_model=List[dict])
async def read_gear_all(
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve all user gear records.

    Parameters:
    - user_id (int): The ID of the authenticated user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - JSONResponse: JSON response containing metadata and user gear records.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.
    """
    try:
        # Query the gear records using SQLAlchemy
        gear_records = (
            db_session.query(Gear)
            .filter(Gear.user_id == user_id)
            .order_by(Gear.nickname)
            .all()
        )

        # Use the gear_record_to_dict function to convert SQLAlchemy objects to dictionaries
        gear_records_dict = [gear_record_to_dict(record) for record in gear_records]

        # Include metadata in the response
        metadata = {"total_records": len(gear_records)}

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": gear_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_gear_all: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/gear/all/{gear_type}", response_model=List[dict])
async def read_gear_all_by_type(
    gear_type: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user gear records filtered by gear type.

    Parameters:
    - gear_type (int): The type of gear to filter by.
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response containing metadata and user gear records filtered by gear type.

    Raises:
    - ValueError: If the gear type is invalid.
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function queries user gear records from the database based on the specified gear type.
    It filters records by both gear type and user ID, includes metadata in the response,
    and returns a JSONResponse with the filtered gear records.

    """
    try:
        # Validate the gear type (example validation)
        if not (1 <= gear_type <= 3):
            # Return an error response if the gear type in invalid
            return create_error_response("UNPROCESSABLE COMTENT", "Invalid gear type. Must be between 1 and 3", 422)

        # Query the gear records using SQLAlchemy and filter by gear type and user ID
        gear_records = (
            db_session.query(Gear)
            .filter(Gear.gear_type == gear_type, Gear.user_id == user_id)
            .order_by(Gear.nickname)
            .all()
        )

        # Use the gear_record_to_dict function to convert SQLAlchemy objects to dictionaries
        gear_records_dict = [gear_record_to_dict(record) for record in gear_records]

        # Include metadata in the response
        metadata = {
            "total_records": len(gear_records),
            "gear_type": gear_type,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": gear_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_gear_all_by_type: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/gear/number")
async def read_gear_number(
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve the total number of user gear records.

    Parameters:
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response containing metadata and the total number of user gear records.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function queries the total number of user gear records from the database,
    includes metadata in the response, and returns a JSONResponse with the total gear count.

    """
    try:
        # Query the number of gear records for the user using SQLAlchemy, filter by user ID and return the count
        gear_count = (
            db_session.query(func.count(Gear.id))
            .filter(Gear.user_id == user_id)
            .scalar()
        )

        # Include metadata in the response
        metadata = {"total_records": 1}

        # Return the queried values using JSONResponse
        return JSONResponse(content={"metadata": metadata, "content": gear_count})

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_gear_number: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get(
    "/gear/all/pagenumber/{pageNumber}/numRecords/{numRecords}",
    response_model=List[dict],
    #tags=["Pagination"],
)
async def read_gear_all_pagination(
    pageNumber: int,
    numRecords: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user gear records with pagination.

    Parameters:
    - pageNumber (int): The page number to retrieve.
    - numRecords (int): The number of records to display per page.
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response containing metadata and user gear records for the specified page.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function queries user gear records from the database with pagination,
    includes metadata in the response, and returns a JSONResponse with the gear records for the specified page.

    """
    try:
        # Use SQLAlchemy to query the gear records with pagination, filter by user ID, order by nickname ascending and return the records
        gear_records = (
            db_session.query(Gear)
            .filter(Gear.user_id == user_id)
            .order_by(Gear.nickname.asc())
            .offset((pageNumber - 1) * numRecords)
            .limit(numRecords)
            .all()
        )

        # Use the gear_record_to_dict function to convert SQLAlchemy objects to dictionaries
        gear_records_dict = [gear_record_to_dict(record) for record in gear_records]

        # Include metadata in the response
        metadata = {
            "total_records": len(gear_records),
            "page_number": pageNumber,
            "num_records": numRecords,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": gear_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_gear_all_pagination: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.get("/gear/nickname/{nickname}", response_model=List[dict])
async def read_gear_nickname(
    nickname: str,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user gear records by nickname.

    Parameters:
    - nickname (str): The nickname to search for in user gear records.
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response containing metadata and user gear records matching the provided nickname.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function queries user gear records from the database by nickname,
    includes metadata in the response, and returns a JSONResponse with the matching gear records.

    """
    try:
        # Define a search term
        partial_nickname = unquote(nickname).replace("+", " ")

        # Use SQLAlchemy to query the gear records by nickname, filter by user ID and nickname, and return the records
        gear_records = (
            db_session.query(Gear)
            .filter(
                Gear.nickname.like(f"%{partial_nickname}%"), Gear.user_id == user_id
            )
            .all()
        )

        # Use the gear_record_to_dict function to convert SQLAlchemy objects to dictionaries
        gear_records_dict = [gear_record_to_dict(record) for record in gear_records]

        # Include metadata in the response
        metadata = {
            "total_records": len(gear_records),
            "nickname": nickname,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": gear_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_gear_nickname: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


# Get gear from id
@router.get("/gear/id/{id}", response_model=List[dict])
async def read_gear_id(
    id: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Retrieve user gear records by ID.

    Parameters:
    - id (int): The ID of the gear record to retrieve.
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response containing metadata and user gear records matching the provided ID.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function queries user gear records from the database by ID,
    includes metadata in the response, and returns a JSONResponse with the matching gear records.

    """
    try:
        # Use SQLAlchemy to query the gear record by ID and filter by user ID and gear ID
        gear_records = (
            db_session.query(Gear).filter(Gear.id == id, Gear.user_id == user_id).all()
        )

        # Use the gear_record_to_dict function to convert SQLAlchemy objects to dictionaries
        gear_records_dict = [gear_record_to_dict(record) for record in gear_records]

        # Include metadata in the response
        metadata = {
            "total_records": len(gear_records),
            "id": id,
        }

        # Return the queried values using JSONResponse
        return JSONResponse(
            content={"metadata": metadata, "content": gear_records_dict}
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error and return an error response
        logger.error(f"Error in read_gear_id: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.post("/gear/create")
async def create_gear(
    gear: GearCreateRequest,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Create a new user gear record.

    Parameters:
    - gear (GearCreateRequest): Pydantic model containing information for creating a new gear record.
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response indicating the success of the gear creation.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function uses the provided GearCreateRequest model to create a new gear record in the database,
    associates it with the authenticated user, and returns a JSONResponse indicating the success of the creation.

    """
    try:
        # Use SQLAlchemy to create a new gear record
        gear_record = Gear(
            brand=unquote(gear.brand).replace("+", " "),
            model=unquote(gear.model).replace("+", " "),
            nickname=unquote(gear.nickname).replace("+", " "),
            gear_type=gear.gear_type,
            user_id=user_id,
            created_at=gear.date,
            is_active=True,
        )

        # Add the gear record to the database using SQLAlchemy
        db_session.add(gear_record)
        db_session.commit()

        # Return a JSONResponse indicating the success of the gear creation
        return JSONResponse(
            content={"message": "Gear created successfully"}, status_code=201
        )

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in create_gear: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.put("/gear/{gear_id}/edit")
async def edit_gear(
    gear_id: int,
    gear: GearEditRequest,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Edit an existing user gear record.

    Parameters:
    - gear_id (int): The ID of the gear record to edit.
    - gear (GearEditRequest): Pydantic model containing information for editing the gear record.
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response indicating the success of the gear edit.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function uses the provided GearEditRequest model to edit an existing gear record in the database,
    verifies ownership, and returns a JSONResponse indicating the success of the edit.

    """
    try:
        # Use SQLAlchemy to query and update the gear record
        gear_record = db_session.query(Gear).filter(Gear.id == gear_id).first()

        # Check if the gear record exists
        if gear_record:
            # Check if the gear record belongs to the user
            if gear_record.user_id == user_id:
                # Update the gear record
                if gear.brand is not None:
                    gear_record.brand = unquote(gear.brand).replace("+", " ")
                if gear.model is not None:
                    gear_record.model = unquote(gear.model).replace("+", " ")
                gear_record.nickname = unquote(gear.nickname).replace("+", " ")
                gear_record.gear_type = gear.gear_type
                gear_record.created_at = gear.date
                gear_record.is_active = gear.is_active

                # Commit the transaction
                db_session.commit()

                # Return a JSONResponse indicating the success of the gear edit
                return JSONResponse(
                    content={"message": "Gear edited successfully"}, status_code=200
                )
            else:
                # Return an error response if the gear record does not belong to the user
                return create_error_response("NOT_FOUND", f"Gear does not belong to user {user_id}. Will not delete", 404)
        else:
            # Return an error response if the gear record is not found
            return create_error_response("NOT_FOUND", "Gear not found", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in edit_gear: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )


@router.delete("/gear/{gear_id}/delete")
async def delete_gear(
    gear_id: int,
    user_id: int = Depends(get_current_user),
    db_session: Session = Depends(get_db_session),
):
    """
    Delete an existing user gear record.

    Parameters:
    - gear_id (int): The ID of the gear record to delete.
    - user_id (int, optional): The ID of the authenticated user (default: extracted from token).
    - db_session (Session, optional): SQLAlchemy database session (default: obtained from dependency).

    Returns:
    - JSONResponse: JSON response indicating the success of the gear deletion.

    Raises:
    - JWTError: If the user is not authenticated.
    - Exception: For other unexpected errors.

    This function deletes an existing gear record from the database,
    verifies ownership, and returns a JSONResponse indicating the success of the deletion.

    """
    try:
        # Use SQLAlchemy to query and delete the gear record
        gear_record = db_session.query(Gear).filter(Gear.id == gear_id).first()

        # Check if the gear record exists
        if gear_record:
            # Check if the gear record belongs to the user
            if gear_record.user_id == user_id:
                # Delete the gear record
                db_session.delete(gear_record)

                # Commit the transaction
                db_session.commit()

                # Return a JSONResponse indicating the success of the gear deletion
                return JSONResponse(
                    content={"message": f"Gear {gear_id} has been deleted"},
                    status_code=200,
                )
            else:
                # Return an error response if the gear record does not belong to the user
                return create_error_response("NOT_FOUND", f"Gear does not belong to user {user_id}. Will not delete", 404)
        else:
            # Return an error response if the gear record is not found
            return create_error_response("NOT_FOUND", "Gear not found", 404)

    except JWTError:
        # Return an error response if the user is not authenticated
        return create_error_response("UNAUTHORIZED", "Unauthorized", 401)
    except Exception as err:
        # Log the error, rollback the transaction, and return an error response
        db_session.rollback()
        logger.error(f"Error in delete_gear: {err}", exc_info=True)
        return create_error_response(
            "INTERNAL_SERVER_ERROR", "Internal Server Error", 500
        )
