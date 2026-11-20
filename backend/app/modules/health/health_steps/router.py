"""FastAPI router for health steps endpoints."""

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
    date_range: core_date_range.DateRangeQuery,
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Look back from today over this interval; ignored when `start_date` or `end_date` is given"),
    ] = None,
) -> core_pagination.Page[health_steps_schema.HealthStepsRead]:
    """Retrieve paginated health steps records for the authenticated user.

    One page of records, newest first, optionally limited to an interval. Access is
    restricted to users with the 'health:read' scope.
    """
    return health_steps_service.list_health_steps(
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
def read_health_steps_chart(
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
    """Chart the authenticated user's steps over an interval.

    One aggregated point per day, week or month depending on the interval, so the response stays small
    however long the history. Access is restricted to users with the 'health:read' scope.
    """
    return health_steps_service.get_health_steps_chart(token_user_id, interval, db, date_range=date_range)


@router.get(
    "/{health_steps_id}",
    response_model=health_steps_schema.HealthStepsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:read"])],
)
def read_health_steps_by_id(
    health_steps_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_steps_schema.HealthStepsRead:
    """Retrieve one of the authenticated user's steps records; its ``ETag`` is the version for ``If-Match``."""
    record = health_steps_service.get_health_steps(token_user_id, health_steps_id, db)
    core_etag.set_etag(response, record.version)
    return record


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
    response: Response,
) -> health_steps_schema.HealthStepsRead:
    """Create health steps data for a user.

    A date that already has a record is answered with a 409; change it with ``PATCH /{id}``.
    """
    created = health_steps_service.create_health_steps(token_user_id, health_steps, db)
    core_location.set_location(response, request, "read_health_steps_by_id", health_steps_id=created.id)
    core_etag.set_etag(response, created.version)
    return created


@router.patch(
    "/{health_steps_id}",
    response_model=health_steps_schema.HealthStepsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_health_steps(
    request: Request,
    health_steps_id: core_dependencies.UuidId,
    health_steps: health_steps_schema.HealthStepsUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_steps_schema.HealthStepsRead:
    """Edit health steps data for a user.

    This endpoint updates existing health steps records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.
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
    health_steps_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a health steps record for the authenticated user.

    This endpoint removes a specific health steps entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.
    """
    # Deletes entry from database
    health_steps_service.delete_health_steps(token_user_id, health_steps_id, db, if_match=if_match)
