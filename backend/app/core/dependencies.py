"""Shared validation dependencies for FastAPI routers."""

from typing import Annotated

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
from fastapi import Depends, Header, HTTPException, Path, status
from sqlalchemy.orm import Session

import core.database as core_database
import core.etag as core_etag
import core.exceptions as core_exceptions

#: A path-parameter id that must be positive. Declared on the parameter's type, so FastAPI rejects a
#: bad value with the standard validation problem document and publishes the bound in OpenAPI.
PositiveId = Annotated[int, Path(gt=0)]

#: The request-scoped database session. Rolled back on an unhandled error and closed afterwards by ``get_db``.
DbSession = Annotated[Session, Depends(core_database.get_db)]


def require_if_match_header(if_match: Annotated[str | None, Header(alias=core_etag.IF_MATCH_HEADER)] = None) -> str:
    """
    Return the request's ``If-Match`` precondition, which a write to a versioned resource must carry.

    Args:
        if_match: The ``If-Match`` header, if the client sent one.

    Returns:
        The raw header value.

    Raises:
        PreconditionRequiredError: When the header is absent (428).
        InvalidInputError: When the header is the wildcard ``*``, which would match any version
            and so defeat the stale-write check; only in-process callers may pass it to a service.
    """
    if if_match is None:
        raise core_exceptions.PreconditionRequiredError()
    if core_etag.WILDCARD in core_etag.parse_if_match(if_match):
        raise core_exceptions.InvalidInputError("If-Match must name the ETag you read, not the wildcard")
    return if_match


#: The ``If-Match`` precondition of a write to a versioned resource; its absence is refused with 428.
IfMatch = Annotated[str, Depends(require_if_match_header)]


def get_storage() -> platform_providers.StorageProvider:
    """
    Return the active platform's blob-storage provider.

    Routers declare it with ``Depends`` so the provider reaches services as an
    argument and a test can override it without patching the runtime.

    Returns:
        The storage provider.
    """
    return platform_runtime.get_active_platform().storage


#: The active platform's blob-storage provider, injected into a route or dependency.
Storage = Annotated[platform_providers.StorageProvider, Depends(get_storage)]


def get_platform_state() -> platform_providers.StateProvider:
    """
    Return the active platform's ephemeral-state provider.

    Routers declare it with ``Depends`` so the provider reaches services and stores as
    an argument and a test can override it without patching the runtime.

    Returns:
        The state provider.
    """
    return platform_runtime.get_state()


#: The active platform's ephemeral-state provider, injected into a route or dependency.
PlatformState = Annotated[platform_providers.StateProvider, Depends(get_platform_state)]


def get_mail() -> platform_providers.MailProvider:
    """
    Return the active platform's outbound-mail provider.

    Routers declare it with ``Depends`` so the provider reaches services as an
    argument and a test can override it without patching the runtime.

    Returns:
        The mail provider.
    """
    return platform_runtime.get_active_platform().mail


def validate_id(identifier: int, min_value: int, message: str) -> None:
    """
    Validate that an integer identifier is above a minimum.

    Args:
        identifier: Identifier value to validate.
        min_value: Minimum exclusive value.
        message: Error detail for invalid values.

    Returns:
        None.

    Raises:
        HTTPException: If the value is not above the minimum.
    """
    if not (int(identifier) > min_value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=message,
        )


def validate_type(type_value: int, min_value: int, max_value: int, message: str) -> None:
    """
    Validate that an integer type is inside an inclusive range.

    Args:
        type_value: Type value to validate.
        min_value: Minimum inclusive value.
        max_value: Maximum inclusive value.
        message: Error detail for invalid values.

    Returns:
        None.

    Raises:
        HTTPException: If the value is outside the range.
    """
    if not (min_value <= int(type_value) <= max_value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=message,
        )


def validate_pagination_values(
    page_number: int,
    num_records: int,
) -> None:
    """
    Validate pagination arguments supplied by callers.

    Args:
        page_number: One-based page number.
        num_records: Number of records per page.

    Returns:
        None.

    Raises:
        HTTPException: If either value is less than one.
    """
    if not (int(page_number) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid page number, must be higher than 0",
        )

    if not (int(num_records) > 0):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid number of records, must be higher than 0",
        )
