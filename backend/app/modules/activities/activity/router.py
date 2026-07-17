"""FastAPI routes for the activities module (authenticated)."""

import calendar
import glob
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
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
import core.dependencies as core_dependencies
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity.event_publishers as activity_event_publishers
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.stats as activities_stats
import modules.auth.dependencies as auth_dependencies
import modules.garmin.activity_utils as garmin_activity_utils
import modules.gears.gear.dependencies as gears_dependencies
import modules.strava.activity_utils as strava_activity_utils
import modules.users.users.dependencies as users_dependencies
import modules.websocket.manager as websocket_manager

# Define the API router
router = APIRouter()


@router.get(
    "/user/{user_id}/week/{week_number}",
    response_model=list[activities_schema.Activity] | None,
)
def read_activities_user_activities_week(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    week_number: int,
    _validate_week_number: Annotated[Callable, Depends(activities_dependencies.validate_week_number)],
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
    # Calculate the start of the requested week
    today = datetime.now(UTC)
    start_of_week = today - timedelta(days=(today.weekday() + 7 * week_number))
    end_of_week = start_of_week + timedelta(days=6)

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(user_id, start_of_week, end_of_week, db, True)
    else:
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id,
            start_of_week,
            end_of_week,
            db,
            False,
            requester_user_id=token_user_id,
        )

    # Check if activities is None
    if activities is None:
        # Return None if activities is None
        return None

    # Return the activities
    return activities


@router.get(
    "/user/{user_id}/thisweek/stats",
    response_model=activities_schema.ActivityStats,
)
def read_activities_user_activities_this_week_stats(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activities_schema.ActivityStats:
    # Calculate the start of the current week
    today = datetime.now(UTC)
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    activities: list[activities_schema.Activity] | None = None

    if user_id == token_user_id:
        # Get all user activities for the requested week if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(user_id, start_of_week, end_of_week, db, True)
    else:
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id,
            start_of_week,
            end_of_week,
            db,
            False,
            requester_user_id=token_user_id,
        )

    # Return the aggregated stats (distance, time, calories) per sport for this week
    if activities:
        return activities_stats.calculate_activity_stats(activities)
    return activities_schema.ActivityStats()


@router.get(
    "/user/{user_id}/thismonth/stats",
    response_model=activities_schema.ActivityStats,
)
def read_activities_user_activities_this_month_stats(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activities_schema.ActivityStats:
    # Calculate the start of the current month
    today = datetime.now(UTC)
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(day=calendar.monthrange(today.year, today.month)[1])
    activities: list[activities_schema.Activity] | None = None

    if user_id == token_user_id:
        # Get all user activities for the requested month if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(user_id, start_of_month, end_of_month, db, True)
    else:
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id,
            start_of_month,
            end_of_month,
            db,
            False,
            requester_user_id=token_user_id,
        )

    # Return the aggregated stats (distance, time, calories) per sport for this month
    if activities:
        return activities_stats.calculate_activity_stats(activities)
    return activities_schema.ActivityStats()


@router.get(
    "/user/{user_id}/thismonth/number",
    response_model=int,
)
def read_activities_user_activities_this_month_number(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
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
    # Calculate the start of the current month
    today = datetime.now(UTC)
    start_of_month = today.replace(day=1)
    end_of_month = start_of_month.replace(day=calendar.monthrange(today.year, today.month)[1])

    if user_id == token_user_id:
        # Get all user activities for the requested month if the user is the owner of the token
        activities = activities_crud.get_user_activities_per_timeframe(user_id, start_of_month, end_of_month, db, True)
    else:
        activities = activities_crud.get_user_activities_per_timeframe(
            user_id,
            start_of_month,
            end_of_month,
            db,
            False,
            requester_user_id=token_user_id,
        )

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/gear/{gear_id}/list",
    response_model=(activities_schema.GearActivitiesListResponse),
    status_code=status.HTTP_200_OK,
)
def read_gear_activities_list(
    gear_id: int,
    _validate_gear_id: Annotated[
        Callable,
        Depends(
            gears_dependencies.validate_gear_id,
        ),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(
            auth_dependencies.check_scopes,
            scopes=["activities:read"],
        ),
    ],
    token_user_id: Annotated[
        int,
        Depends(
            auth_dependencies.get_sub_from_access_token,
        ),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    page_number: Annotated[
        int | None,
        Query(
            description="Page number",
        ),
    ] = None,
    num_records: Annotated[
        int | None,
        Query(
            description="Records per page",
        ),
    ] = None,
) -> activities_schema.GearActivitiesListResponse:
    """
    Retrieve paginated gear activities with total
    count.

    Args:
        gear_id: Gear ID.
        _validate_gear_id: Validates gear ID exists.
        _check_scopes: Validates activities:read.
        token_user_id: Authenticated user ID.
        db: Database session.
        page_number: Optional page number.
        num_records: Optional records per page.

    Returns:
        GearActivitiesListResponse with total count
        and paginated records.
    """
    total = activities_crud.get_gear_activities_count_by_user_id(
        token_user_id,
        gear_id,
        db,
    )
    records = activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
        token_user_id,
        gear_id,
        page_number or 1,
        num_records or 10,
        db,
    )

    return activities_schema.GearActivitiesListResponse(
        total=total,
        num_records=num_records,
        page_number=page_number,
        records=records or [],
    )


@router.get(
    "/gear/{gear_id}",
    response_model=list[activities_schema.Activity] | None,
)
def read_activities_gear_activities(
    gear_id: int,
    _validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
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
    # Get the activities for the gear
    return activities_crud.get_user_activities_by_gear_id_and_user_id(token_user_id, gear_id, db)


@router.get(
    "/gear/{gear_id}/number",
    response_model=int,
)
def read_activities_gear_activities_number(
    gear_id: int,
    _validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
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
    # Get the number of activities for the gear
    activities = activities_crud.get_user_activities_by_gear_id_and_user_id(token_user_id, gear_id, db)
    if activities is None:
        return 0
    return len(activities)


@router.get(
    "/gear/{gear_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,
)
def read_activities_gear_activities_with_pagination(
    gear_id: int,
    _validate_gear_id: Annotated[Callable, Depends(gears_dependencies.validate_gear_id)],
    page_number: int,
    num_records: int,
    _validate_pagination_values: Annotated[Callable, Depends(core_dependencies.validate_pagination_values)],
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
    # Get the activities for the gear with pagination
    return activities_crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
        token_user_id, gear_id, page_number, num_records, db
    )


@router.get(
    "/number",
    response_model=int,
)
def read_activities_user_activities_number(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    # Added dependencies for optional query parameters
    _validate_activity_type: Annotated[Callable, Depends(activities_dependencies.validate_activity_type)],
    # Added optional filter query parameters
    activity_type: int | None = Query(None, alias="type"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    name_search: str | None = Query(None),
):
    # Get the number of activities for the user
    activities = activities_crud.get_user_activities(
        user_id=token_user_id,
        db=db,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
    )

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/types",
    response_model=dict | None,
)
def read_activities_types(
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
    return activities_crud.get_distinct_activity_types_for_user(token_user_id, db)


@router.get(
    "/user/{user_id}/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,
)
def read_activities_user_activities_pagination(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    page_number: int,
    num_records: int,
    validate_pagination_values: Annotated[Callable, Depends(core_dependencies.validate_pagination_values)],
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    # Added dependencies for optional query parameters
    _validate_activity_type: Annotated[Callable, Depends(activities_dependencies.validate_activity_type)],
    _validate_sort_by: Annotated[Callable, Depends(activities_dependencies.validate_sort_by)],
    _validate_sort_order: Annotated[Callable, Depends(activities_dependencies.validate_sort_order)],
    # Added optional filter query parameters
    activity_type: int | None = Query(None, alias="type"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    name_search: str | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str | None = Query(None),
):
    user_is_owner = True
    if token_user_id != user_id:
        user_is_owner = False
    # Get and return the activities for the user with pagination and filters
    return activities_crud.get_user_activities_with_pagination(
        user_id=user_id,
        db=db,
        page_number=page_number,
        num_records=num_records,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        name_search=name_search,
        sort_by=sort_by,
        sort_order=sort_order,
        user_is_owner=user_is_owner,
        requester_user_id=token_user_id,
    )


@router.get(
    "/user/{user_id}/followed/page_number/{page_number}/num_records/{num_records}",
    response_model=list[activities_schema.Activity] | None,  # Keep old response model for now
)
def read_activities_followed_user_activities_pagination(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    page_number: int,
    num_records: int,
    _validate_pagination_values: Annotated[Callable, Depends(core_dependencies.validate_pagination_values)],
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
    # Enforce ownership: a user can only read their own following feed
    # to prevent IDOR (OWASP A01).
    if user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    # Get the activities for the following users with pagination
    return activities_crud.get_user_following_activities_with_pagination(token_user_id, page_number, num_records, db)


@router.get(
    "/user/{user_id}/followed/number",
    response_model=int,
)
def read_activities_followed_user_activities_number(
    user_id: int,
    _validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
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
    # Enforce ownership: a user can only read their own following count
    # to prevent IDOR (OWASP A01).
    if user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
    # Get the number of activities for the following users
    activities = activities_crud.get_user_following_activities(token_user_id, db)

    # Check if activities is None and return 0 if it is
    if activities is None:
        return 0

    # Return the number of activities
    return len(activities)


@router.get(
    "/refresh",
    response_model=list[activities_schema.Activity] | None,
)
async def read_activities_user_activities_refresh(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    ws_manager: Annotated[
        websocket_manager.WebSocketManager,
        Depends(websocket_manager.get_websocket_manager),
    ],
):
    # Set the activities to empty list
    activities = []

    # Get the strava activities for the user for the last 24h
    strava_activities = await strava_activity_utils.get_user_strava_activities_by_dates(
        start_date=datetime.now(UTC) - timedelta(days=1),
        end_date=datetime.now(UTC),
        user_id=token_user_id,
        ws_manager=ws_manager,
        db=db,
    )

    # Get the garmin activities for the user for the last 24h
    garmin_activities = await garmin_activity_utils.get_user_garminconnect_activities_by_dates(
        start_date=datetime.now(UTC) - timedelta(days=1),
        end_date=datetime.now(UTC),
        user_id=token_user_id,
        ws_manager=ws_manager,
        db=db,
    )

    # Extend the activities to the list
    if strava_activities is not None:
        activities.extend(strava_activities)

    if garmin_activities is not None:
        activities.extend(garmin_activities)

    # Filter out None values from the activities list
    activities = [activity for activity in activities if activity is not None]

    # Return the activities or None if the list is empty
    return activities if activities else None


@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity | None,
)
def read_activities_activity_from_id(
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
    # Get the activity from the database and return it
    return activities_crud.get_activity_by_id_from_user_id_or_has_visibility(activity_id, token_user_id, db)


@router.get(
    "/name/contains/{name}",
    response_model=list[activities_schema.Activity] | None,
)
def read_activities_contain_name(
    name: str,
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
    # Get the activities from the database by name
    return activities_crud.get_activities_if_contains_name(name, token_user_id, db)


@router.put(
    "/edit",
    response_model=activities_schema.Activity,
)
def edit_activity(
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    activity_attributes: activities_schema.ActivityEdit,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:write"])],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Update the activity in the database
    updated = activities_crud.edit_activity(token_user_id, activity_attributes, db)

    # Publish the domain fact so subscribers can react to the edit (reindex, feed
    # refresh, ...) without the route knowing who reacts. ``changed`` is derived
    # from the fields the client actually submitted. Best-effort; the session
    # enables durable outbox delivery when durable jobs are enabled.
    changed = sorted(field for field in activity_attributes.model_dump(exclude_unset=True) if field != "id")
    activity_event_publishers.publish_activity_updated(
        activity_attributes.id,
        token_user_id,
        changed=changed,
        db=db,
    )

    return updated


@router.put(
    "/visibility/{visibility}",
    response_model=dict[str, str | int],
)
def edit_activity_visibility(
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
    # Update the activities in the database
    updated = activities_crud.edit_user_activities_visibility(token_user_id, visibility, db)

    # Return success message with rowcount
    return {
        "detail": (f"Visibility changed to {visibility} for all user activities"),
        "updated": updated or 0,
    }


@router.delete(
    "/{activity_id}/delete",
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
