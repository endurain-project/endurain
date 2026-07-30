"""FastAPI routes for the activities module (authenticated).

RESTful surface. Route handlers are thin: they validate,
delegate the read/stats/feed orchestration to :mod:`activity/service.py`, and
return. Literal paths are declared before ``/{activity_id}`` so FastAPI matches
them first.
"""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Security,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.service as activities_service
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.dependencies as gears_dependencies
import modules.users.users.dependencies as users_dependencies

# Default page size when a list request omits pagination.
_DEFAULT_NUM_RECORDS = 25
# Hard cap on the client-requested page size, bounding query and
# serialization cost per request (defense against resource exhaustion).
_MAX_NUM_RECORDS = 200

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
    return activities_crud.get_distinct_activity_types_for_user(token_user_id, db)


@router.get(
    "/feed",
    response_model=activities_schema.ActivityPage,
)
def list_following_feed(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=_MAX_NUM_RECORDS)] = None,
):
    """List the authenticated user's following feed, with the matching total."""
    return activities_service.page_following_feed(
        token_user_id,
        token_user_id,
        page_number or 1,
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
def edit_activities(
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
    if body.visibility is None:
        # An empty patch is a client bug, not a no-op worth reporting as success.
        raise core_exceptions.InvalidInputError("No supported field to update was provided")

    updated = activities_crud.edit_user_activities_visibility(token_user_id, body.visibility, db)
    return activities_schema.VisibilityUpdateResponse(
        detail=f"Visibility changed to {body.visibility} for all user activities",
        updated=updated or 0,
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
):
    """Read a single activity the requester owns or is permitted to see."""
    activity = activities_crud.get_activity_by_id_from_user_id_or_has_visibility(activity_id, token_user_id, db)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity {activity_id} not found",
        )
    return activity


@router.patch(
    "/{activity_id}",
    response_model=activities_schema.Activity,
)
def edit_activity(
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
):
    """Apply partial updates to one of the authenticated user's activities."""
    return activities_crud.edit_activity(token_user_id, activity_id, activity_attributes, db)


@router.delete(
    "/{activity_id}",
    response_model=activities_schema.ActivityMessageResponse,
)
def delete_activity(
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
) -> activities_schema.ActivityMessageResponse:
    """Delete one of the authenticated user's activities."""
    # Delete the activity and publish ``activity.deleted`` atomically: the delete
    # is staged (commit=False) and the publisher owns the single commit, so when
    # durable jobs are enabled the outbox row is written in the *same* transaction
    # as the delete. A crash can no longer leave the row deleted but the cleanup
    # event unpublished (which would orphan the thumbnail / source-file blobs).
    # The route stays ignorant of who reacts; on the best-effort (no durable jobs)
    # path the commit runs first and any bus-dispatch failure is swallowed.
    #
    # Ownership lives in the delete's WHERE clause (404 when the activity is
    # missing *or* owned by someone else), so there is no read-then-delete gap
    # and no route-level precondition that a future caller could forget.
    activities_crud.delete_activity(activity_id, token_user_id, db, commit=False)
    activity_event_publishers.publish_activity_deleted(activity_id, token_user_id, db, commit=db.commit)

    # Return success message
    return activities_schema.ActivityMessageResponse(detail=f"Activity {activity_id} deleted successfully")
