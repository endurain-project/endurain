"""FastAPI router for health fasting endpoints.

This module defines the API endpoints for managing fasting sessions,
including CRUD operations, active fast tracking, and statistics.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[health_fasting_schema.HealthFastingRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_fasting_all_pagination(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Filter by goal interval"),
    ] = None,
) -> core_pagination.Page[health_fasting_schema.HealthFastingRead]:
    """Retrieve health fasting records for the authenticated user.

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
    return health_fasting_service.list_health_fasting(
        token_user_id, db, page_number=page.page_number, num_records=page.num_records, interval=interval
    )


@router.get(
    "/active",
    response_model=health_fasting_schema.HealthFastingRead | None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_active_fasting(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_fasting_schema.HealthFastingRead | None:
    """Retrieve the active fasting session for the authenticated user.

    Args:
        token_user_id: User ID from the access token.
        db: Database session dependency.
        response: The response, which carries the session's ETag.

    Returns:
        Active HealthFastingRead if exists, None otherwise.
    """
    active = health_fasting_service.get_active_fasting(token_user_id, db)
    if active is not None:
        core_etag.set_etag(response, active.version)
    return active


@router.get(
    "/stats",
    response_model=health_fasting_schema.HealthFastingStatsResponse,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_fasting_stats(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingStatsResponse:
    """Retrieve fasting statistics for the authenticated user.

    Args:
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        HealthFastingStatsResponse with statistics.
    """
    return health_fasting_service.get_fasting_stats(token_user_id, db)


@router.get(
    "/{health_fasting_id}",
    response_model=health_fasting_schema.HealthFastingRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_fasting_by_id(
    health_fasting_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_fasting_schema.HealthFastingRead:
    """Retrieve a specific fasting record by ID.

    Args:
        health_fasting_id: ID of the fasting record.
        token_user_id: User ID from the access token.
        db: Database session dependency.
        response: The response, which carries the record's ETag.

    Returns:
        HealthFastingRead for the specified record.

    Raises:
        NotFoundError: If record not found.
    """
    record = health_fasting_service.get_health_fasting(token_user_id, health_fasting_id, db)
    core_etag.set_etag(response, record.version)
    return record


@router.post(
    "",
    response_model=health_fasting_schema.HealthFastingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_fasting(
    request: Request,
    health_fasting: health_fasting_schema.HealthFastingCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_fasting_schema.HealthFastingRead:
    """Create a new fasting session.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting: Fasting data to create.
        token_user_id: User ID from the access token.
        db: Database session dependency.

    Returns:
        Created HealthFastingRead record.

    Raises:
        ConflictError: If user already has an active fast.
    """
    return health_fasting_service.create_health_fasting(token_user_id, health_fasting, db)


@router.patch(
    "/{health_fasting_id}",
    response_model=health_fasting_schema.HealthFastingRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_fasting(
    request: Request,
    health_fasting_id: core_dependencies.PositiveId,
    health_fasting: health_fasting_schema.HealthFastingUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_fasting_schema.HealthFastingRead:
    """Edit an existing fasting record.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting_id: ID of the record to change.
        health_fasting: Fasting data to update.
        token_user_id: User ID from the access token.
        db: Database session dependency.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        Updated HealthFastingRead record.
    """
    updated = health_fasting_service.edit_health_fasting(
        token_user_id, health_fasting_id, health_fasting, db, if_match=if_match
    )
    core_etag.set_etag(response, updated.version)
    return updated


@router.post(
    "/{health_fasting_id}/complete",
    response_model=health_fasting_schema.HealthFastingRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def complete_health_fasting(
    request: Request,
    health_fasting_id: core_dependencies.PositiveId,
    complete_data: health_fasting_schema.HealthFastingComplete,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_fasting_schema.HealthFastingRead:
    """Complete or end a fasting session.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting_id: ID of the fasting record to complete.
        complete_data: Completion data with end time and status.
        token_user_id: User ID from the access token.
        db: Database session dependency.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        Updated HealthFastingRead record.
    """
    ended = health_fasting_service.complete_health_fasting(
        token_user_id, health_fasting_id, complete_data, db, if_match=if_match
    )
    core_etag.set_etag(response, ended.version)
    return ended


@router.delete(
    "/{health_fasting_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_fasting(
    request: Request,
    health_fasting_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a fasting record.

    Args:
        request: The incoming request, read by the rate limiter.
        health_fasting_id: ID of the fasting record to delete.
        token_user_id: User ID from the access token.
        if_match: The ``If-Match`` precondition.
        db: Database session dependency.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    health_fasting_service.delete_health_fasting(token_user_id, health_fasting_id, db, if_match=if_match)
