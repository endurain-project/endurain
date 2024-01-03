from sqlalchemy.orm import Session
from db.db import Session as BaseSession
from fastapi.responses import JSONResponse
from controllers import sessionController
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

# Define the OAuth2 scheme for handling bearer tokens
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_db_session() -> Session:
    """
    Get a SQLAlchemy database session.

    Returns:
    - Session: SQLAlchemy database session.

    Yields:
    - Session: SQLAlchemy database session to the calling function.

    # Note: The session is automatically committed and closed by FastAPI at the end of the request.
    """
    db_session = BaseSession()
    try:
        yield db_session
    finally:
        db_session.close()


def get_current_user(
    token: str = Depends(oauth2_scheme), db_session: Session = Depends(get_db_session)
):
    """
    Get the ID of the current authenticated user.

    Parameters:
    - token (str): The authentication token for the user.
    - db_session (Session): SQLAlchemy database session.

    Returns:
    - int: The ID of the current authenticated user.

    Raises:
    - JWTError: If the authentication token is invalid or expired.
    - Exception: For other unexpected errors.
    """
    sessionController.validate_token(db_session, token)
    return sessionController.get_user_id_from_token(token)


# Standardized error response function
def create_error_response(code: str, message: str, status_code: int):
    """
    Create a JSON error response.

    Parameters:
    - code (str): Error code to be included in the response.
    - message (str): Error message to be included in the response.
    - status_code (int): HTTP status code for the response.

    Returns:
    - JSONResponse: JSON response containing the specified error information.
    """
    return JSONResponse(
        content={"error": {"code": code, "message": message}}, status_code=status_code
    )
