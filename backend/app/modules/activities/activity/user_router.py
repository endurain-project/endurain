"""FastAPI routes for a user's activities (authenticated), served under ``/users``."""

from typing import Annotated

from fastapi import APIRouter, Query, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/{user_id}/activities/stats",
    response_model=activity_schema.ActivityStatsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def read_user_activity_stats(
    user_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    period: Annotated[str, Query(pattern="^(week|month)$")] = "week",
    anchor_date: Annotated[
        activity_dependencies.WindowDate | None,
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
    "/{user_id}/activities",
    response_model=activity_schema.ActivityPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_user_activities(
    user_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
    activity_type: activity_dependencies.ActivityTypeFilter = None,
    start_date: Annotated[activity_dependencies.WindowDate | None, Query()] = None,
    end_date: Annotated[activity_dependencies.WindowDate | None, Query()] = None,
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
