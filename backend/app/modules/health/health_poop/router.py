"""FastAPI router for health poop (bowel movement) endpoints.

This module defines the API endpoints for managing bowel movement
records, including CRUD operations with pagination and filtering.
"""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
    Response,
    Security,
    status,
)

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[health_poop_schema.HealthPoopRead],
    status_code=status.HTTP_200_OK,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:read"],
        )
    ],
)
def read_health_poop_all_pagination(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Filter by goal interval"),
    ] = None,
) -> core_pagination.Page[health_poop_schema.HealthPoopRead]:
    """Retrieve paginated poop records for the user.

    One page of records, newest first, optionally limited to an interval. Access is
    restricted to users with the 'health:read' scope.

    Args:
        token_user_id: The ID of the authenticated user extracted from the access token.
        db: Database session for executing queries.
        page: The requested page and page size.
        interval: Optional filter to retrieve records within a specific goal interval.

    Returns:
        The page of records with the total matching the interval.
    """
    return health_poop_service.list_health_poop(
        token_user_id, db, page_number=page.page_number, num_records=page.num_records, interval=interval
    )


@router.get(
    "/{health_poop_id}",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_200_OK,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:read"],
        )
    ],
)
def read_health_poop_by_id(
    health_poop_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_poop_schema.HealthPoopRead:
    """Retrieve a specific poop record by ID.

    Args:
        health_poop_id: ID of the poop record.
        token_user_id: User ID from the access token.
        db: Database session dependency.
        response: The response, which carries the record's ETag.

    Returns:
        HealthPoopRead for the specified record.

    Raises:
        NotFoundError: If the user has no such record.
    """
    record = health_poop_service.get_health_poop(token_user_id, health_poop_id, db)
    response.headers["ETag"] = core_etag.format_etag(record.version)
    return record


@router.post(
    "",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_poop(
    request: Request,
    health_poop: health_poop_schema.HealthPoopCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_poop_schema.HealthPoopRead:
    """Create a new poop record for the user.

    Unlike other health modules, multiple poop records can exist
    per day.

    Args:
        request: The incoming request, read by the rate limiter.
        health_poop: Poop data to create.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created HealthPoopRead record.
    """
    return health_poop_service.create_health_poop(token_user_id, health_poop, db)


@router.patch(
    "/{health_poop_id}",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_200_OK,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_poop(
    request: Request,
    health_poop_id: core_dependencies.PositiveId,
    health_poop: health_poop_schema.HealthPoopUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_poop_schema.HealthPoopRead:
    """Edit an existing poop record.

    Args:
        request: The incoming request, read by the rate limiter.
        health_poop_id: ID of the record to change.
        health_poop: Poop data to update.
        token_user_id: User ID from the access token.
        db: Database session dependency.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        Updated HealthPoopRead record.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    updated = health_poop_service.edit_health_poop(token_user_id, health_poop_id, health_poop, db, if_match=if_match)
    response.headers["ETag"] = core_etag.format_etag(updated.version)
    return updated


@router.delete(
    "/{health_poop_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        )
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_poop(
    request: Request,
    health_poop_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a poop record for the authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        health_poop_id: ID of the poop record to delete.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Raises:
        NotFoundError: If the user has no such record.
    """
    health_poop_service.delete_health_poop(token_user_id, health_poop_id, db)
