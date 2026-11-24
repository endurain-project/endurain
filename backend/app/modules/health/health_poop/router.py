"""FastAPI router for health poop (bowel movement) endpoints.

This module defines the API endpoints for managing bowel movement
records, including CRUD operations with pagination and filtering.
"""

from typing import Annotated

from fastapi import (
    APIRouter,
    Query,
    Request,
    Response,
    Security,
    status,
)

import core.date_range as core_date_range
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.idempotency as core_idempotency
import core.location as core_location
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.health.constants as health_constants
import modules.health.health_poop.schema as health_poop_schema
import modules.health.health_poop.service as health_poop_service
import modules.health.schema as health_schema

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=core_pagination.Page[health_poop_schema.HealthPoopRead],
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
    page: core_pagination.ListPage,
    date_range: core_date_range.DateRangeQuery,
    interval: Annotated[
        health_constants.Interval | None,
        Query(description="Look back from today over this interval; ignored when `start_date` or `end_date` is given"),
    ] = None,
) -> core_pagination.Page[health_poop_schema.HealthPoopRead]:
    """Retrieve paginated poop records for the user.

    One page of records, newest first, optionally limited to an interval. Access is
    restricted to users with the 'health:read' scope.
    """
    return health_poop_service.list_health_poop(
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
def read_health_poop_chart(
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
    """Chart the authenticated user's daily bowel-movement frequency over an interval.

    One aggregated point per day, week or month depending on the interval, so the response stays small
    however long the history. Declared before the ``/{health_poop_id}`` route so ``chart`` is not read as an id.
    Access is restricted to users with the 'health:read' scope.
    """
    return health_poop_service.get_health_poop_chart(token_user_id, interval, db, date_range=date_range)


@router.get(
    "/{health_poop_id}",
    response_model=health_poop_schema.HealthPoopRead,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:read"],
        )
    ],
)
def read_health_poop_by_id(
    health_poop_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_poop_schema.HealthPoopRead:
    """Retrieve a specific poop record by ID."""
    record = health_poop_service.get_health_poop(token_user_id, health_poop_id, db)
    core_etag.set_etag(response, record.version)
    return record


@router.post(
    "",
    response_model=health_poop_schema.HealthPoopRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["health:write"],
        ),
        core_idempotency.Idempotent,
    ],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_health_poop(
    request: Request,
    health_poop: health_poop_schema.HealthPoopCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> health_poop_schema.HealthPoopRead:
    """Create a new poop record for the user.

    Unlike other health modules, multiple poop records can exist
    per day.
    """
    created = health_poop_service.create_health_poop(token_user_id, health_poop, db)
    core_location.set_location(response, request, "read_health_poop_by_id", health_poop_id=created.id)
    core_etag.set_etag(response, created.version)
    return created


@router.patch(
    "/{health_poop_id}",
    response_model=health_poop_schema.HealthPoopRead,
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
    health_poop_id: core_dependencies.UuidId,
    health_poop: health_poop_schema.HealthPoopUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> health_poop_schema.HealthPoopRead:
    """Edit an existing poop record."""
    updated = health_poop_service.edit_health_poop(token_user_id, health_poop_id, health_poop, db, if_match=if_match)
    core_etag.set_etag(response, updated.version)
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
    health_poop_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a poop record for the authenticated user."""
    health_poop_service.delete_health_poop(token_user_id, health_poop_id, db, if_match=if_match)
