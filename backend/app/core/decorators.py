"""Core decorators project wide."""

from functools import wraps
from typing import Callable, TypeVar, ParamSpec

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import core.logger as core_logger

# Type variables for decorator
P = ParamSpec("P")
T = TypeVar("T")


def handle_db_errors(func: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator to handle SQLAlchemy database errors consistently.

    Catches SQLAlchemyError exceptions, logs them, and converts to
    HTTPException with 500 status. Allows HTTPException and
    IntegrityError to pass through for function-specific handling.

    Args:
        func: The CRUD function to wrap.

    Returns:
        Wrapped function with error handling.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except (HTTPException, IntegrityError):
            # Let these exceptions pass through for function-specific handling
            raise
        except SQLAlchemyError as db_err:
            core_logger.print_to_log(
                f"Database error in {func.__name__}: {db_err}",
                "error",
                exc=db_err,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred",
            ) from db_err

    return wrapper
