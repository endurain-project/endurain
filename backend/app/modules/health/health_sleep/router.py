"""FastAPI router for health sleep endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, status

import core.date_range as core_date_range
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.idempotency as core_idempotency
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
    response_model=core_pagination.Page[health_sleep_schema.HealthSleepListItem],
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
    has_resting_heart_rate: Annotated[
        bool | None,
        Query(description="Keep only nights with (`true`) or without (`false`) a resting heart rate"),
    ] = None,
) -> core_pagination.Page[health_sleep_schema.HealthSleepListItem]:
    """Retrieve health sleep records for the authenticated user.

    One page of records, newest first, optionally limited to an interval and to nights with or without a
    resting heart rate; the total counts the same records. A record carries ``has_sleep_stages``, not its
    stages, which are on `GET /health/sleep/{health_sleep_id}`. Access is restricted to users with the
    'health:read' scope.
    """
    return health_sleep_service.list_health_sleep(
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        interval=interval,
        date_range=date_range,
        has_resting_heart_rate=has_resting_heart_rate,
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
    health_sleep_id: core_dependencies.UuidId,
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["health:write"]), core_idempotency.Idempotent],
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
    health_sleep_id: core_dependencies.UuidId,
    health_sleep: health_sleep_schema.HealthSleepUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_sleep_schema.HealthSleepRead:
    """Edit health sleep data for a user.

    This endpoint updates existing health sleep records in the database for the authenticated user.
    Requires 'health:write' scope for authorization.
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
    health_sleep_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a health sleep record for the authenticated user.

    This endpoint removes a specific health sleep entry from the database for the user
    identified by the access token. The user must have 'health:write' scope permission.
    """
    # Deletes entry from database
    health_sleep_service.delete_health_sleep(token_user_id, health_sleep_id, db, if_match=if_match)
