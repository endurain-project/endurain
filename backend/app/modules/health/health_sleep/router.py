"""FastAPI router for health sleep endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, status

import core.date_range as core_date_range
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.location as core_location
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.service as health_sleep_service
import modules.health.schema as health_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[health_sleep_schema.HealthSleepRead],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_sleep_all_pagination(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    date_range: core_date_range.DateRangeQuery,
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Look back from today over this interval; ignored when `start_date` or `end_date` is given"),
    ] = None,
) -> core_pagination.Page[health_sleep_schema.HealthSleepRead]:
    """Retrieve health sleep records for the authenticated user.

    One page of records, newest first, optionally limited to an interval. Access is
    restricted to users with the 'health:read' scope.

    Args:
        token_user_id: The ID of the authenticated user extracted from the access token.
        db: Database session for executing queries.
        page: The requested page and page size.
        interval: Optional interval looking back from today; ignored when a date range is given.
        date_range: Optional inclusive start and end dates, which replace the interval.

    Returns:
        The page of records with the total matching the interval.
    """
    return health_sleep_service.list_health_sleep(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        interval=interval,
        date_range=date_range,
    )


@router.get(
    "/chart",
    response_model=health_schema.HealthChartSeries,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_sleep_chart(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    date_range: core_date_range.DateRangeQuery,
    interval: Annotated[
        health_constants.Interval,
        Query(
            description="Interval to chart, looking back from today; ignored when `start_date` or `end_date` is given"
        ),
    ] = health_constants.Interval.LAST_7_DAYS,
) -> health_schema.HealthChartSeries:
    """Chart the authenticated user's total sleep seconds over an interval.

    One aggregated point per day, week or month depending on the interval, so the response stays small
    however long the history. Access is restricted to users with the 'health:read' scope.

    Args:
        token_user_id: The ID of the authenticated user extracted from the access token.
        db: Database session for executing queries.
        interval: The window to chart, looking back from today; ignored when a date range is given.
        date_range: Optional inclusive start and end dates to chart instead of the interval.

    Returns:
        The interval's bucket size and its points, oldest first.
    """
    return health_sleep_service.get_health_sleep_chart(token_user_id, interval, db, date_range=date_range)


@router.get(
    "/chart/resting-heart-rate",
    response_model=health_schema.HealthChartSeries,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_sleep_resting_heart_rate_chart(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    date_range: core_date_range.DateRangeQuery,
    interval: Annotated[
        health_constants.Interval,
        Query(
            description="Interval to chart, looking back from today; ignored when `start_date` or `end_date` is given"
        ),
    ] = health_constants.Interval.LAST_7_DAYS,
) -> health_schema.HealthChartSeries:
    """Chart the authenticated user's resting heart rate over an interval.

    One aggregated point per day, week or month depending on the interval, so the response stays small
    however long the history. Access is restricted to users with the 'health:read' scope.

    Args:
        token_user_id: The ID of the authenticated user extracted from the access token.
        db: Database session for executing queries.
        interval: The window to chart, looking back from today; ignored when a date range is given.
        date_range: Optional inclusive start and end dates to chart instead of the interval.

    Returns:
        The interval's bucket size and its points, oldest first.
    """
    return health_sleep_service.get_health_sleep_resting_heart_rate_chart(
        token_user_id, interval, db, date_range=date_range
    )


@router.get(
    "/{health_sleep_id}",
    response_model=health_sleep_schema.HealthSleepRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_sleep_by_id(
    health_sleep_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_sleep_schema.HealthSleepRead:
    """Retrieve one of the authenticated user's sleep records; its ``ETag`` is the version for ``If-Match``."""
    record = health_sleep_service.get_health_sleep(token_user_id, health_sleep_id, db)
    core_etag.set_etag(response, record.version)
    return record


@router.post(
    "",
    response_model=health_sleep_schema.HealthSleepRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_sleep(
    request: Request,
    health_sleep: health_sleep_schema.HealthSleepCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_sleep_schema.HealthSleepRead:
    """Create health sleep data for a user.

    A date that already has a record is answered with a 409; change it with ``PATCH /{id}``.

    Args:
        request: The incoming request, read by the rate limiter.
        health_sleep (health_sleep_schema.HealthSleepCreate): The health sleep data to create,
            including the date and sleep duration.
        token_user_id (int): The ID of the authenticated user extracted from the
            access token.
        db (Session): Database session dependency for database operations.
        response: The response, whose ``Location`` names where the record is read.

    Returns:
        health_sleep_schema.HealthSleepRead: The created health sleep data.

    """
    created = health_sleep_service.create_health_sleep(token_user_id, health_sleep, db)
    core_location.set_location(response, request, "read_health_sleep_by_id", health_sleep_id=created.id)
    core_etag.set_etag(response, created.version)
    return created


@router.patch(
    "/{health_sleep_id}",
    response_model=health_sleep_schema.HealthSleepRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_sleep(
    request: Request,
    health_sleep_id: core_dependencies.PositiveId,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_sleep_schema.HealthSleepRead:
    """Edit health sleep data for a user.

    This endpoint updates existing health sleep records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.

    Args:
        request: The incoming request, read by the rate limiter.
        health_sleep_id: ID of the record to change.
        health_sleep (health_sleep_schema.HealthSleepUpdate): The health sleep data to be updated,
            containing the new values for the health sleep record.
        token_user_id (int): The user ID extracted from the JWT access token, used to identify
            the user making the request.
        db (Session): Database session dependency for performing database operations.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition.

    Returns:
        health_sleep_schema.HealthSleepRead: The updated health sleep record with the new values
            as stored in the database.

    Raises:
        NotFoundError: If the user has no such record.
        PreconditionFailedError: If the record changed since the client read it.
    """
    updated = health_sleep_service.edit_health_sleep(
        token_user_id, health_sleep_id, health_sleep, db, if_match=if_match
    )
    core_etag.set_etag(response, updated.version)
    return updated


@router.delete(
    "/{health_sleep_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_health_sleep(
    request: Request,
    health_sleep_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a health sleep record for the authenticated user.

    This endpoint removes a specific health sleep entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.

    Args:
        request: The incoming request, read by the rate limiter.
        health_sleep_id (int): The unique identifier of the health sleep record to delete.
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
    health_sleep_service.delete_health_sleep(token_user_id, health_sleep_id, db, if_match=if_match)
