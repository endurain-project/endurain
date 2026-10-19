"""FastAPI routes for the activities module (authenticated).

RESTful surface. Route handlers are thin transport adapters: they validate,
delegate to :mod:`activity/service.py`, and return. They hold no domain rule and
no persistence orchestration, and they never reach past the service into ``crud``
or the event publishers (the transport rule in the module-structure guide).
Literal paths are declared before ``/{activity_id}`` so FastAPI matches them
first.
"""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    Query,
    Request,
    Response,
    Security,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=activity_schema.ActivityPage,
)
def list_own_activities(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    activity_type: activity_dependencies.ActivityTypeFilter = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    name_search: Annotated[str | None, Query(alias="name")] = None,
    sort_by: activity_dependencies.SortBy = None,
    sort_order: activity_dependencies.SortOrder = None,
) -> activity_schema.ActivityPage:
    """List the authenticated user's activities, with the matching total."""
    return activity_service.page_user_activities(
        token_user_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get(
    "/types",
    response_model=dict[int, str],
)
def list_activity_types(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> dict[int, str]:
    """Return the distinct activity types the user has recorded, keyed by type code."""
    return activity_service.list_activity_types(token_user_id, db)


@router.get(
    "/feed",
    response_model=activity_schema.ActivityFeedPage,
)
def list_following_feed(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    cursor: Annotated[str | None, Query()] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
) -> activity_schema.ActivityFeedPage:
    """List a keyset slice of the authenticated user's following feed."""
    return activity_service.scroll_following_feed(
        token_user_id,
        cursor,
        num_records or core_pagination.DEFAULT_NUM_RECORDS,
        db,
    )


@router.get(
    "/gears/{gear_id}",
    response_model=activity_schema.ActivityPage,
)
def list_gear_activities(
    gear_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
) -> activity_schema.ActivityPage:
    """List the authenticated user's activities for a gear, with the matching total."""
    return activity_service.page_gear_activities(
        token_user_id,
        gear_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )


@router.get(
    "/users/{user_id}/stats",
    response_model=activity_schema.ActivityStatsRead,
)
def read_user_activity_stats(
    user_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    period: Annotated[str, Query(pattern="^(week|month)$")] = "week",
    anchor_date: Annotated[
        date | None,
        Query(
            alias="date",
            description=(
                "The caller's local calendar date, used to decide which week or month "
                "is current. Defaults to today in the caller's configured timezone."
            ),
        ),
    ] = None,
) -> activity_schema.ActivityStatsRead:
    """Aggregate per-sport stats for a user's current ``week`` or ``month``."""
    return activity_service.period_stats(user_id, period, token_user_id, db, anchor=anchor_date)


@router.get(
    "/users/{user_id}",
    response_model=activity_schema.ActivityPage,
)
def list_user_activities(
    user_id: core_dependencies.PositiveId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.list_page_params)],
    activity_type: activity_dependencies.ActivityTypeFilter = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    name_search: Annotated[str | None, Query(alias="name")] = None,
    sort_by: activity_dependencies.SortBy = None,
    sort_order: activity_dependencies.SortOrder = None,
) -> activity_schema.ActivityPage:
    """List another user's visible activities, with the matching total."""
    return activity_service.page_user_activities(
        user_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.patch(
    "",
    response_model=activity_schema.VisibilityUpdateRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_activities(
    request: Request,
    body: activity_schema.ActivitiesBulkEdit,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_schema.VisibilityUpdateRead:
    """Apply a bulk edit across all of the authenticated user's activities.

    A PATCH on the collection with the change in the body, rather than the
    previous ``PUT /visibility/{visibility}``: the value being set is data, not
    an identifier, and PUT implied a full replacement of a resource that does
    not exist at that path. The body shape also leaves room for a second
    bulk-editable field without another endpoint.

    Rejected as invalid input when the body asks for no change at all.
    """
    updated = activity_service.bulk_edit_activities(token_user_id, body, db)
    return activity_schema.VisibilityUpdateRead(
        detail=f"Visibility changed to {body.visibility} for all user activities",
        updated=updated,
    )


@router.get(
    "/{activity_id}",
    response_model=activity_schema.ActivityRead,
)
def read_activity(
    activity_id: activity_dependencies.ActivityId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    response: Response,
) -> activity_schema.ActivityRead:
    """Read a single activity the requester owns or is permitted to see."""
    activity = activity_service.get_activity(activity_id, token_user_id, db)
    if activity.version is not None:
        # The tag the client echoes back in If-Match when it later saves.
        response.headers["ETag"] = core_etag.format_etag(activity.version)
    return activity


@router.patch(
    "/{activity_id}",
    response_model=activity_schema.ActivityRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_activity(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    activity_attributes: activity_schema.ActivityEdit,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    response: Response,
    if_match: Annotated[str | None, Header(alias=core_etag.IF_MATCH_HEADER)] = None,
) -> activity_schema.ActivityRead:
    """Apply partial updates to one of the authenticated user's activities.

    Send ``If-Match`` with the ETag from the read to make the write conditional;
    a stale tag is refused with 412 rather than silently overwriting whoever
    saved in between.
    """
    activity = activity_service.edit_activity(activity_id, token_user_id, activity_attributes, db, if_match=if_match)
    if activity.version is not None:
        response.headers["ETag"] = core_etag.format_etag(activity.version)
    return activity


@router.delete(
    "/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_activity(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """Delete one of the authenticated user's activities.

    Answers ``204`` with no body: the resource is gone, and the status says so.
    """
    activity_service.delete_activity(activity_id, token_user_id, db)
