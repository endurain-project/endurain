"""Core decorators project wide."""

import inspect
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, NoReturn, overload

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


def _find_db_session(*args, **kwargs) -> Session | None:
    """
    Find a SQLAlchemy Session instance in function arguments.

    Args:
        *args: Positional arguments to search.
        **kwargs: Keyword arguments to search.

    Returns:
        The first Session instance found, or None.
    """
    for value in args:
        if isinstance(value, Session):
            return value
    for value in kwargs.values():
        if isinstance(value, Session):
            return value
    return None


def _rollback_session(func_name: str, db_session: Session | None) -> None:
    """
    Attempt a rollback on the database session, logging any failure.

    Args:
        func_name: Name of the calling function (for log context).
        db_session: Database session to rollback, if any.
    """
    if db_session is not None:
        try:
            db_session.rollback()
        except Exception as rollback_err:
            logger.error(f"Rollback failed in {func_name}: {type(rollback_err).__name__}", exc_info=rollback_err)


def _handle_db_error(db_err: SQLAlchemyError, func_name: str, db_session: Session | None) -> NoReturn:
    """
    Handle database errors consistently.

    Performs rollback, logs the error securely, and raises ``ProcessingError``.

    Args:
        db_err: The database error that occurred.
        func_name: Name of the function where the error occurred.
        db_session: Database session to rollback, if any.

    Raises:
        ProcessingError: Always, after logging and rollback. The API boundary
            renders it as the same 500 the previous ``HTTPException`` produced,
            but the persistence layer no longer decides that — which is what lets
            the durable-job worker, which serves no HTTP, handle a database
            failure without importing a web framework.
    """
    _rollback_session(func_name, db_session)

    # Log only the exception class name — SQLAlchemy error strings
    # frequently embed the offending SQL statement and parameter values,
    # which can leak PII / credentials into logs (OWASP A09).
    logger.error(f"Database error in {func_name}: {type(db_err).__name__}", exc_info=db_err)

    raise core_exceptions.ProcessingError("Database error occurred") from db_err


@overload
def handle_db_errors[T, **P](func: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, Coroutine[Any, Any, T]]: ...


@overload
def handle_db_errors[T, **P](func: Callable[P, T]) -> Callable[P, T]: ...


def handle_db_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator to handle SQLAlchemy database errors consistently.

    Catches SQLAlchemyError exceptions, logs them, and converts to
    ``core.exceptions.ProcessingError`` (a transport-agnostic domain error, not
    an HTTP response). Allows ``DomainError``, ``HTTPException`` (transitional —
    see ``sync_wrapper``) and ``IntegrityError`` to pass through for
    caller-specific handling.

    Automatically calls rollback on the database session if found
    in function parameters.

    Supports both synchronous and asynchronous functions.

    Args:
        func: The CRUD function to wrap (can be sync or async).

    Returns:
        Wrapped function with error handling.
    """
    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except core_exceptions.DomainError:
                raise
            except HTTPException:
                # TRANSITIONAL: see sync_wrapper.
                raise
            except IntegrityError:
                _rollback_session(func.__name__, _find_db_session(*args, **kwargs))
                raise
            except SQLAlchemyError as db_err:
                db_session = _find_db_session(*args, **kwargs)
                _handle_db_error(db_err, func.__name__, db_session)

        return async_wrapper

    @wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except core_exceptions.DomainError:
            raise
        except HTTPException:
            # TRANSITIONAL: modules not yet converted still raise HTTPException
            # from their CRUD. Drop this arm once none do.
            raise
        except IntegrityError:
            _rollback_session(func.__name__, _find_db_session(*args, **kwargs))
            raise
        except SQLAlchemyError as db_err:
            db_session = _find_db_session(*args, **kwargs)
            _handle_db_error(db_err, func.__name__, db_session)

    return sync_wrapper
