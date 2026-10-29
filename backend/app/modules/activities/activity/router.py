"""FastAPI routes for the activities module (authenticated).

RESTful surface. Route handlers are thin transport adapters: they validate,
delegate to :mod:`activity/service.py`, and return. They hold no domain rule and
no persistence orchestration, and they never reach past the service into ``crud``
or the event publishers (the transport rule in the module-structure guide).
Literal paths are declared before ``/{activity_id}`` so FastAPI matches them
first.
"""

from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Query,
    Request,
    Response,
    Security,
    status,
)

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.activities.activity.bulk_edit_job_service as activity_bulk_edit_job_service
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
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_types(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
) -> dict[int, str]:
    """Return the distinct activity types the user has recorded, keyed by type code."""
    return activity_service.list_activity_types(token_user_id, db)


@router.get(
    "/feed",
    response_model=activity_schema.ActivityFeedPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_following_feed(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    cursor: Annotated[str | None, Query()] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
) -> activity_schema.ActivityFeedPage:
    """List a keyset slice of the authenticated user's following feed.

    The slice also carries the public profile of each owner on it in ``users`` (the projection
    ``GET /users/id/{user_id}`` returns), so a token with ``activities:read`` alone receives it too.
    """
    return activity_service.scroll_following_feed(
        token_user_id,
        cursor,
        num_records or core_pagination.DEFAULT_NUM_RECORDS,
        db,
    )


@router.patch(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=activity_schema.ActivitiesBulkEditStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_activities(
    request: Request,
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
    ``GET /activities/bulk-edit`` for the outcome.

    Args:
        request: The incoming request, read by the rate limiter.
        body: The fields to apply; only those present are changed.
        token_user_id: User ID from the access token.
        states: Shared store of the edit's state.
        db: Database session dependency.

    Returns:
        The edit's initial status.

    Raises:
        InvalidInputError: When the body asks for no change at all. An empty
            patch is a client bug, not a no-op worth reporting as success.
        ConflictError: When a bulk edit is already pending.
    """
    if body.visibility is None:
        raise core_exceptions.InvalidInputError("No supported field to update was provided")
    return activity_bulk_edit_job_service.request_visibility_edit(token_user_id, body.visibility, states, db)


@router.get(
    "/bulk-edit",
    response_model=activity_schema.ActivitiesBulkEditStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def read_bulk_edit_status(
    token_user_id: auth_dependencies.CurrentUserId,
    states: activity_dependencies.ActivityBulkEditStateStoreDep,
) -> activity_schema.ActivitiesBulkEditStatus:
    """Report where the authenticated user's bulk edit is.

    Args:
        token_user_id: User ID from the access token.
        states: Shared store of the edit's state.

    Returns:
        The edit's status.

    Raises:
        NotFoundError: If no bulk edit is recorded or it has expired.
    """
    return activity_bulk_edit_job_service.get_visibility_edit_status(token_user_id, states)


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
