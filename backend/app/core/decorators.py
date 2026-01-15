"""Core decorators project wide."""

from functools import wraps
from typing import Callable, TypeVar, ParamSpec, cast

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

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

    Automatically calls rollback on the database session if found
    in function parameters.

    Args:
        func: The CRUD function to wrap.

    Returns:
        Wrapped function with error handling.
    """

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except HTTPException:
            raise
        except (SQLAlchemyError, IntegrityError) as db_err:
            # Find any Session instance
            db_session = None

            for value in list(args) + list(kwargs.values()):
                if isinstance(value, Session):
                    db_session = value
                    break

            if db_session is not None:
                try:
                    cast(Session, db_session).rollback()
                except Exception:
                    pass

            core_logger.print_to_log(
                f"Database error in {func.__name__}: {db_err}",
                "error",
                exc=db_err,
            )

            # Let IntegrityError bubble if you want custom handling upstream
            if isinstance(db_err, IntegrityError):
                raise

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database error occurred",
            ) from db_err

    return wrapper
