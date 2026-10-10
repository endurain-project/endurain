"""FastAPI routes for the activities module (authenticated).

RESTful surface. Route handlers are thin transport adapters: they validate,
delegate to :mod:`activity/service.py`, and return. They hold no domain rule and
no persistence orchestration, and they never reach past the service into ``crud``
or the event publishers — enforced by the ``activities-router-delegates``
import-linter contract. Literal paths are declared before ``/{activity_id}`` so
FastAPI matches them first.
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
import core.etag as core_etag
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.service as activities_service
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.dependencies as gears_dependencies
import modules.users.users.dependencies as users_dependencies

# Default page size when a list request omits pagination.
_DEFAULT_NUM_RECORDS = core_pagination.DEFAULT_NUM_RECORDS
# Hard cap on the client-requested page size, bounding query and
# serialization cost per request (defense against resource exhaustion).
_MAX_NUM_RECORDS = core_pagination.MAX_NUM_RECORDS

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=activities_schema.ActivityPage,
)
def list_own_activities(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    _validate_activity_type: Annotated[Callable, Depends(activities_dependencies.validate_activity_type)],
    _validate_sort_by: Annotated[Callable, Depends(activities_dependencies.validate_sort_by)],
    _validate_sort_order: Annotated[Callable, Depends(activities_dependencies.validate_sort_order)],
    activity_type: Annotated[int | None, Query(alias="type")] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    name_search: Annotated[str | None, Query(alias="name")] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query()] = None,
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
):
    """List the authenticated user's activities, with the matching total."""
    return activities_service.page_user_activities(
        token_user_id,
        token_user_id,
        page_number or 1,
        num_records or _DEFAULT_NUM_RECORDS,
        db,
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
    return activities_service.list_activity_types(token_user_id, db)


@router.get(
    "/feed",
    response_model=activities_schema.ActivityFeedPage,
)
def list_following_feed(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    cursor: Annotated[str | None, Query()] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
):
    """List a keyset slice of the authenticated user's following feed."""
    return activities_service.scroll_following_feed(
        token_user_id,
        token_user_id,
        cursor,
        num_records or _DEFAULT_NUM_RECORDS,
        db,
    )


@router.get(
    "/gears/{gear_id}",
    response_model=activities_schema.ActivityPage,
)
def list_gear_activities(
    gear_id: int,
    _validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
):
    """List the authenticated user's activities for a gear, with the matching total."""
    return activities_service.page_gear_activities(
        token_user_id,
        gear_id,
        page_number or 1,
        num_records or _DEFAULT_NUM_RECORDS,
        db,
    )


@router.get(
    "/users/{user_id}/stats",
    response_model=activities_schema.ActivityStats,
)
def read_user_activity_stats(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
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
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's current ``week`` or ``month``."""
    return activities_service.period_stats(user_id, period, token_user_id, db, anchor_date)


@router.get(
    "/users/{user_id}",
    response_model=activities_schema.ActivityPage,
)
def list_user_activities(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    _validate_activity_type: Annotated[Callable, Depends(activities_dependencies.validate_activity_type)],
    _validate_sort_by: Annotated[Callable, Depends(activities_dependencies.validate_sort_by)],
    _validate_sort_order: Annotated[Callable, Depends(activities_dependencies.validate_sort_order)],
    activity_type: Annotated[int | None, Query(alias="type")] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    name_search: Annotated[str | None, Query(alias="name")] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query()] = None,
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
):
    """List another user's visible activities, with the matching total."""
    return activities_service.page_user_activities(
        user_id,
        token_user_id,
        page_number or 1,
        num_records or _DEFAULT_NUM_RECORDS,
        db,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.patch(
    "",
    response_model=activities_schema.VisibilityUpdateResponse,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_activities(
    request: Request,
    body: activities_schema.ActivitiesBulkEdit,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activities_schema.VisibilityUpdateResponse:
    """Apply a bulk edit across all of the authenticated user's activities.

    A PATCH on the collection with the change in the body, rather than the
    previous ``PUT /visibility/{visibility}``: the value being set is data, not
    an identifier, and PUT implied a full replacement of a resource that does
    not exist at that path. The body shape also leaves room for a second
    bulk-editable field without another endpoint.

    Args:
        body: The fields to apply; only those present are changed.
        token_user_id: Authenticated user ID.
        _check_scopes: Scope validation dependency.
        db: Database session dependency.

    Returns:
        How many activities changed.

    Raises:
        InvalidInputError: If the body asks for no change at all.
    """
    updated = activities_service.bulk_edit_activities(token_user_id, body, db)
    return activities_schema.VisibilityUpdateResponse(
        detail=f"Visibility changed to {body.visibility} for all user activities",
        updated=updated,
    )


@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity,
)
def read_activity(
    activity_id: int,
    _validate_activity_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
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
):
    """Read a single activity the requester owns or is permitted to see."""
    activity = activities_service.get_activity(activity_id, token_user_id, db)
    if activity.version is not None:
        # The tag the client echoes back in If-Match when it later saves.
        response.headers["ETag"] = core_etag.format_etag(activity.version)
    return activity


@router.patch(
    "/{activity_id}",
    response_model=activities_schema.Activity,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_activity(
    request: Request,
    activity_id: int,
    _validate_activity_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    activity_attributes: activities_schema.ActivityEdit,
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
):
    """Apply partial updates to one of the authenticated user's activities.

    Send ``If-Match`` with the ETag from the read to make the write conditional;
    a stale tag is refused with 412 rather than silently overwriting whoever
    saved in between.
    """
    activity = activities_service.edit_activity(activity_id, token_user_id, activity_attributes, db, if_match)
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
    activity_id: int,
    _validate_activity_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
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

    Answers ``204`` with no body, like every other delete in the API. It used to
    return ``200`` with a confirmation sentence, which is a representation of
    nothing: the resource is gone, and the status already says so.
    """
    activities_service.delete_activity(activity_id, token_user_id, db)
