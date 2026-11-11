"""FastAPI routes for the activities module (authenticated).

RESTful surface. Route handlers are thin transport adapters: they validate,
delegate to :mod:`activity/service.py`, and return. They hold no domain rule and
no persistence orchestration, and they never reach past the service into ``crud``
or the event publishers (the transport rule in the module-structure guide).
Literal paths are declared before ``/{activity_id}`` so FastAPI matches them
first.
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
import core.exceptions as core_exceptions
import core.location as core_location
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import core.types as core_types
import modules.activities.activity.bulk_edit_constants as bulk_edit_constants
import modules.activities.activity.bulk_edit_job_service as activity_bulk_edit_job_service
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
import modules.auth.dependencies as auth_dependencies

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=activity_schema.ActivityPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_own_activities(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    date_range: core_date_range.DateRangeQuery,
    activity_type: activity_dependencies.ActivityTypeFilter = None,
    name_contains: Annotated[
        str | None,
        Query(min_length=1, max_length=250, description="Keep only activities whose name contains this text"),
    ] = None,
    sort_by: activity_dependencies.SortBy = None,
    sort_order: activity_dependencies.SortOrder = None,
    gear_id: Annotated[
        int | None,
        Query(gt=0, le=core_types.INT32_MAX, description="Keep only the activities recorded with this gear"),
    ] = None,
) -> activity_schema.ActivityPage:
    """List the authenticated user's activities, with the matching total."""
    return activity_service.page_user_activities(
        token_user_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
        activity_type=activity_type,
        start_date=date_range.start_date,
        end_date=date_range.end_date,
        name_search=name_contains,
        sort_by=sort_by,
        sort_order=sort_order,
        gear_id=gear_id,
    )


@router.get(
    "/types",
    response_model=dict[activity_constants.ActivityType, str],
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_types(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> dict[activity_constants.ActivityType, str]:
    """Return the distinct activity types the user has recorded, keyed by type with the English name as value."""
    return activity_service.list_activity_types(token_user_id, db)


@router.get(
    "/feed",
    response_model=activity_schema.ActivityFeedPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_feed(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    cursor: Annotated[str | None, Query()] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
    scope: Annotated[
        activity_constants.FeedScope,
        Query(description="`following` lists the users the caller follows; `mine` lists the caller's own activities"),
    ] = activity_constants.FeedScope.FOLLOWING,
) -> activity_schema.ActivityFeedPage:
    """List a keyset slice of the authenticated user's following feed, or of their own activities.

    With ``scope=mine`` the slice holds the caller's own activities of every visibility, newest first.
    The slice also carries the public profile of each owner on it in ``users`` (the projection
    ``GET /users/{user_id}`` returns), so a token with ``activities:read`` alone receives it too.
    """
    return activity_service.scroll_feed(
        token_user_id,
        cursor,
        num_records or core_pagination.DEFAULT_NUM_RECORDS,
        db,
        scope,
    )


@router.patch(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_schema.ActivitiesBulkEditStatus,
    responses=core_location.ACCEPTED_RESPONSE,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_activities(
    request: Request,
    response: Response,
    body: activity_schema.ActivitiesBulkEdit,
    token_user_id: auth_dependencies.CurrentUserId,
    states: activity_dependencies.ActivityBulkEditStateStoreDep,
    db: core_dependencies.DbSession,
) -> activity_schema.ActivitiesBulkEditStatus:
    """Queue a bulk edit across all of the authenticated user's activities.

    A PATCH on the collection with the change in the body, rather than the
    previous ``PUT /visibility/{visibility}``: the value being set is data, not
    an identifier, and PUT implied a full replacement of a resource that does
    not exist at that path. The body shape also leaves room for a second
    bulk-editable field without another endpoint.

    The edit can touch a whole library, so it runs as a background job: poll
    ``GET /jobs/{job_id}`` for the outcome.

    Args:
        request: The incoming request, read by the rate limiter.
        response: The response, which names the job and when to poll it.
        body: The fields to apply; only those present are changed.
        token_user_id: User ID from the access token.
        states: Shared store of the edit's state.
        db: Database session dependency.

    Returns:
        The edit's initial status.

    Raises:
        InvalidInputError: When the body asks for no change at all. An empty
            patch is a client bug, not a no-op worth reporting as success.
        JobAlreadyRunningError: When a bulk edit is already pending.
    """
    if body.visibility is None:
        raise core_exceptions.InvalidInputError("No supported field to update was provided")
    edit = activity_bulk_edit_job_service.request_visibility_edit(token_user_id, body.visibility.stored, states, db)
    core_location.set_job_location(response, request, edit.id, bulk_edit_constants.BULK_EDIT_POLL_SECONDS)
    return edit


@router.get(
    "/{activity_id}",
    response_model=activity_schema.ActivityRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def read_activity(
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> activity_schema.ActivityRead:
    """Read a single activity the requester owns or is permitted to see."""
    activity = activity_service.get_activity(activity_id, token_user_id, db)
    if activity.version is not None:
        # The tag the client echoes back in If-Match when it later saves.
        core_etag.set_etag(response, activity.version)
    return activity


@router.patch(
    "/{activity_id}",
    response_model=activity_schema.ActivityRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_activity(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    activity_attributes: activity_schema.ActivityEdit,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> activity_schema.ActivityRead:
    """Apply partial updates to one of the authenticated user's activities.

    Send ``If-Match`` with the ETag from the read to make the write conditional;
    a stale tag is refused with 412 rather than silently overwriting whoever
    saved in between.
    """
    activity = activity_service.edit_activity(activity_id, token_user_id, activity_attributes, db, if_match=if_match)
    if activity.version is not None:
        core_etag.set_etag(response, activity.version)
    return activity


@router.delete(
    "/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_activity(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete one of the authenticated user's activities.

    Answers ``204`` with no body: the resource is gone, and the status says so.
    Send ``If-Match`` with the activity's ``version`` as an ETag; a stale tag is refused with 412.
    """
    activity_service.delete_activity(activity_id, token_user_id, db, if_match=if_match)
