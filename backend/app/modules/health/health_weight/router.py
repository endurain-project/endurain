"""FastAPI router for health weight endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.service as health_weight_service
import modules.health.schema as health_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[health_weight_schema.HealthWeightRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_weight_all_pagination(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Filter by goal interval"),
    ] = None,
) -> core_pagination.Page[health_weight_schema.HealthWeightRead]:
    """Retrieve paginated health weight records for the authenticated user.

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
    return health_weight_service.list_health_weight(
        token_user_id, db, page_number=page.page_number, num_records=page.num_records, interval=interval
    )


@router.get(
    "/chart",
    response_model=health_schema.HealthChartSeries,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_weight_chart(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    interval: Annotated[
        health_constants.Interval,
        Query(description="Interval to chart"),
    ] = health_constants.Interval.LAST_7_DAYS,
) -> health_schema.HealthChartSeries:
    """Chart the authenticated user's weight over an interval.

    One aggregated point per day, week or month depending on the interval, so the response stays small
    however long the history. Access is restricted to users with the 'health:read' scope.

    Args:
        token_user_id: The ID of the authenticated user extracted from the access token.
        db: Database session for executing queries.
        interval: The window to chart.

    Returns:
        The interval's bucket size and its points, oldest first.
    """
    return health_weight_service.get_health_weight_chart(token_user_id, interval, db)


@router.post(
    "",
    response_model=health_weight_schema.HealthWeightRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_weight(
    request: Request,
    health_weight: health_weight_schema.HealthWeightCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_weight_schema.HealthWeightRead:
    """Create a health weight record for the authenticated user.

    A date that already has a record is answered with a 409; change it with ``PATCH /{id}``.

    Args:
        request: The incoming request, read by the rate limiter.
        health_weight (health_weight_schema.HealthWeightCreate): The health weight data to create.
            Must include a date field.
        token_user_id (int): The ID of the authenticated user extracted from the access token.
        db (Session): Database session dependency for performing database operations.

    Returns:
        health_weight_schema.HealthWeightRead: The created health weight record.

    """
    return health_weight_service.create_health_weight(token_user_id, health_weight, db)


@router.patch(
    "/{health_weight_id}",
    response_model=health_weight_schema.HealthWeightRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_weight(
    request: Request,
    health_weight_id: core_dependencies.PositiveId,
    health_weight: health_weight_schema.HealthWeightUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_weight_schema.HealthWeightRead:
    """Edit a health weight entry for the authenticated user.

    This endpoint allows users with 'health:write' scope to update an existing
    health weight record in the database.

    Args:
        request: The incoming request, read by the rate limiter.
        health_weight_id: ID of the record to change.
        health_weight (health_weight_schema.HealthWeight): The health weight data
            to be updated, containing the weight information and associated metadata.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for executing database operations.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated health weight record from the database.

    Raises:
        PermissionDeniedError: If the record names another user.
        NotFoundError: If the entry doesn't exist.
    """
    updated = health_weight_service.edit_health_weight(
        token_user_id, health_weight_id, health_weight, db, if_match=if_match
    )
    core_etag.set_etag(response, updated.version)
    return updated


@router.delete(
    "/{health_weight_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_weight(
    request: Request,
    health_weight_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a health weight entry for the authenticated user.

    This endpoint allows users to delete their own health weight records. It requires
    the 'health:write' scope for authorization.

    Args:
        request: The incoming request, read by the rate limiter.
        health_weight_id (int): The unique identifier of the health weight entry to delete.
        token_user_id (int): The user ID extracted from the access token, used to ensure
            users can only delete their own weight entries.
        if_match: The ``If-Match`` precondition.
        db (Session): Database session dependency for performing database operations.

    Returns:
        None: This function does not return any value upon successful deletion.

    Raises:
        PreconditionFailedError: If the record changed since the client read it.
        NotFoundError: If the entry doesn't exist for the user.
    """
    health_weight_service.delete_health_weight(token_user_id, health_weight_id, db, if_match=if_match)
