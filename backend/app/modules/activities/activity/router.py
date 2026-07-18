"""FastAPI routes for the activities module (authenticated).

RESTful surface (module rework plan §12). Route handlers are thin: they validate,
delegate the read/stats/feed orchestration to :mod:`activity/service.py`, and
return. Literal paths are declared before ``/{activity_id}`` so FastAPI matches
them first.
"""

import glob
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

import core.config as core_config
import core.database as core_database
import core.file_uploads as core_file_uploads
import core.logger as core_logger
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

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=list[activities_schema.Activity] | int | None,
)
def list_own_activities(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    _validate_activity_type: Annotated[Callable, Depends(activities_dependencies.validate_activity_type)],
    _validate_sort_by: Annotated[Callable, Depends(activities_dependencies.validate_sort_by)],
    _validate_sort_order: Annotated[Callable, Depends(activities_dependencies.validate_sort_order)],
    count: Annotated[bool, Query(description="Return the total count instead of the records")] = False,
    activity_type: Annotated[int | None, Query(alias="type")] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    name_search: Annotated[str | None, Query(alias="name")] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_order: Annotated[str | None, Query()] = None,
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1)] = None,
):
    """List (or count with ``?count=true``) the authenticated user's activities."""
    if count:
        return activities_service.count_user_activities(
            token_user_id,
            db,
            activity_type=activity_type,
            start_date=start_date,
            end_date=end_date,
            name_search=name_search,
        )
    return activities_service.list_user_activities_paginated(
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
    response_model=dict | None,
)
def list_activity_types(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Return the distinct activity types the user has recorded."""
    return activities_crud.get_distinct_activity_types_for_user(token_user_id, db)


@router.get(
    "/feed",
    response_model=list[activities_schema.Activity] | int | None,
)
def list_following_feed(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    count: Annotated[bool, Query(description="Return the total count instead of the records")] = False,
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1)] = None,
):
    """List (or count) the authenticated user's following feed."""
    if count:
        return activities_service.count_following_feed(token_user_id, token_user_id, db)
    return activities_service.get_following_feed(
        token_user_id,
        token_user_id,
        page_number or 1,
        num_records or _DEFAULT_NUM_RECORDS,
        db,
    )


@router.get(
    "/gears/{gear_id}",
    response_model=list[activities_schema.Activity] | int | None,
)
def list_gear_activities(
    gear_id: int,
    _validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    count: Annotated[bool, Query(description="Return the total count instead of the records")] = False,
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1)] = None,
):
    """List (or count) the authenticated user's activities for a gear."""
    if count:
        return activities_service.count_gear_activities(token_user_id, gear_id, db)
    return activities_service.list_gear_activities(token_user_id, gear_id, page_number, num_records, db)


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
) -> activities_schema.ActivityStats:
    """Aggregate per-sport stats for a user's current ``week`` or ``month``."""
    return activities_service.period_stats(user_id, period, token_user_id, db)


@router.get(
    "/users/{user_id}",
    response_model=list[activities_schema.Activity] | None,
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
    num_records: Annotated[int | None, Query(ge=1)] = None,
):
    """List another user's activities that are visible to the requester."""
    return activities_service.list_user_activities_paginated(
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


@router.put(
    "/visibility/{visibility}",
    response_model=dict[str, str | int],
)
def edit_activities_visibility(
    visibility: int,
    _validate_visibility: Annotated[Callable, Depends(activities_dependencies.validate_visibility)],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Set the visibility of all the authenticated user's activities."""
    updated = activities_crud.edit_user_activities_visibility(token_user_id, visibility, db)
    return {
        "detail": (f"Visibility changed to {visibility} for all user activities"),
        "updated": updated or 0,
    }


@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity | None,
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
    return activities_crud.get_activity_by_id_from_user_id_or_has_visibility(activity_id, token_user_id, db)


@router.put(
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
    # The path id is authoritative; ignore any id sent in the body.
    activity_attributes.id = activity_id

    updated = activities_crud.edit_activity(token_user_id, activity_attributes, db)

    # Publish the domain fact so subscribers can react to the edit (reindex, feed
    # refresh, ...) without the route knowing who reacts. ``changed`` is derived
    # from the fields the client actually submitted. Best-effort; the session
    # enables durable outbox delivery when durable jobs are enabled.
    changed = sorted(field for field in activity_attributes.model_dump(exclude_unset=True) if field != "id")
    activity_event_publishers.publish_activity_updated(
        activity_id,
        token_user_id,
        changed=changed,
        db=db,
    )

    return updated


@router.delete(
    "/{activity_id}",
    response_model=dict[str, str],
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
):
    """Delete one of the authenticated user's activities."""
    # Get the activity by id from user id
    activity = activities_crud.get_activity_by_id_from_user_id(activity_id, token_user_id, db)

    # Check if activity is None and raise an HTTPException with a 404 Not Found status code if it is
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Activity ID {activity_id} for user {token_user_id} not found",
        )

    # Delete the activity
    activities_crud.delete_activity(activity_id, db)

    # Publish the domain fact so each subsystem removes the artifacts it owns
    # (the map thumbnail today; media/search-index/... later). The route stays
    # ignorant of who reacts and publishing is best-effort — it never blocks or
    # fails the delete. The session enables durable outbox delivery when durable
    # jobs are enabled.
    activity_event_publishers.publish_activity_deleted(activity_id, token_user_id, db)

    # This activity's own processed files are removed here, in a worker thread,
    # to avoid blocking the event loop with potentially slow disk I/O.
    def _cleanup_processed_files() -> None:
        # Define the search pattern using the file ID (e.g., '1.*')
        pattern = f"{core_config.FILES_PROCESSED_DIR}/{activity_id}.*"
        for file in glob.glob(pattern):
            # Path-bounded removal — refuses to delete anything that
            # resolves outside FILES_PROCESSED_DIR (defense in depth
            # against crafted activity IDs or symlinks).
            try:
                core_file_uploads.safe_remove_within(file, base_dir=core_config.FILES_PROCESSED_DIR)
            except HTTPException as fs_err:
                core_logger.print_to_log(
                    f"Refused to delete file outside processed dir {file}: {fs_err.detail}",
                    "warning",
                )

    _cleanup_processed_files()

    # Return success message
    return {"detail": f"Activity {activity_id} deleted successfully"}
