"""FastAPI router for health steps endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_steps.service as health_steps_service
import modules.health.schema as health_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[health_steps_schema.HealthStepsRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_steps_all_pagination(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Filter by goal interval"),
    ] = None,
) -> core_pagination.Page[health_steps_schema.HealthStepsRead]:
    """Retrieve paginated health steps records for the authenticated user.

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
    return health_steps_service.list_health_steps(
        token_user_id, db, page_number=page.page_number, num_records=page.num_records, interval=interval
    )


@router.get(
    "/chart",
    response_model=health_schema.HealthChartSeries,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_steps_chart(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    interval: Annotated[
        health_constants.Interval,
        Query(description="Interval to chart"),
    ] = health_constants.Interval.LAST_7_DAYS,
) -> health_schema.HealthChartSeries:
    """Chart the authenticated user's steps over an interval.

    One aggregated point per day, week or month depending on the interval, so the response stays small
    however long the history. Access is restricted to users with the 'health:read' scope.

    Args:
        token_user_id: The ID of the authenticated user extracted from the access token.
        db: Database session for executing queries.
        interval: The window to chart.

    Returns:
        The interval's bucket size and its points, oldest first.
    """
    return health_steps_service.get_health_steps_chart(token_user_id, interval, db)


@router.post(
    "",
    response_model=health_steps_schema.HealthStepsRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_steps(
    request: Request,
    health_steps: health_steps_schema.HealthStepsCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> health_steps_schema.HealthStepsRead:
    """Create health steps data for a user.

    A date that already has a record is answered with a 409; change it with ``PATCH /{id}``.

    Args:
        request: The incoming request, read by the rate limiter.
        health_steps (health_steps_schema.HealthSteps): The health steps data to create,
            including the date and step count.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for database operations.

    Returns:
        health_steps_schema.HealthSteps: The created health steps data.

    """
    return health_steps_service.create_health_steps(token_user_id, health_steps, db)


@router.patch(
    "/{health_steps_id}",
    response_model=health_steps_schema.HealthStepsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_steps(
    request: Request,
    health_steps_id: core_dependencies.PositiveId,
    health_steps: health_steps_schema.HealthStepsUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_steps_schema.HealthStepsRead:
    """Edit health steps data for a user.

    This endpoint updates existing health steps records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.

    Args:
        request: The incoming request, read by the rate limiter.
        health_steps_id: ID of the record to change.
        health_steps (health_steps_schema.HealthSteps): The health steps data to be updated,
            containing the new values for the health steps record.
        token_user_id (int): The user ID extracted from the JWT access token, used to identify
            the user making the request.
        db (Session): Database session dependency for performing database operations.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        health_steps_schema.HealthSteps: The updated health steps record with the new values
            as stored in the database.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    # Updates the health_steps in the database and returns it
    updated = health_steps_service.edit_health_steps(
        token_user_id, health_steps_id, health_steps, db, if_match=if_match
    )
    core_etag.set_etag(response, updated.version)
    return updated


@router.delete(
    "/{health_steps_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_steps(
    request: Request,
    health_steps_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a health steps record for the authenticated user.

    This endpoint removes a specific health steps entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.

    Args:
        request: The incoming request, read by the rate limiter.
        health_steps_id (int): The unique identifier of the health steps record to delete.
        token_user_id (int): The user ID extracted from the access token.
        if_match: The ``If-Match`` precondition.
        db (Session): Database session dependency for executing the delete operation.

    Returns:
        None: This function does not return a value.

    Raises:
        PreconditionFailedError: If the record changed since the client read it.
        NotFoundError: If the user has no such record.
    """
    # Deletes entry from database
    health_steps_service.delete_health_steps(token_user_id, health_steps_id, db, if_match=if_match)
