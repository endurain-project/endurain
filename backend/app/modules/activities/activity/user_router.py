"""FastAPI routes for a user's activities (authenticated), served under ``/users``."""

from typing import Annotated

from fastapi import APIRouter, Query, Security

import core.date_range as core_date_range
import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.activities.activity.constants as activity_constants
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
    user_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    period: Annotated[activity_constants.StatsPeriod, Query()] = activity_constants.StatsPeriod.WEEK,
    anchor_date: Annotated[
        core_date_range.WindowDate | None,
        Query(
            alias="date",
            description=(
                "The caller's local calendar date, used to decide which week or month "
                "is current. Defaults to today in the caller's configured timezone."
            ),
        ),
    ] = None,
) -> activity_schema.ActivityStatsRead:
    """Aggregate per-sport stats for a user's current ``week`` or ``month``.

    Another user's stats are answered 404 when that user does not exist, is inactive or awaits approval.
    """
    return activity_service.period_stats(user_id, period, token_user_id, db, anchor=anchor_date)


@router.get(
    "/{user_id}/activities",
    response_model=activity_schema.ActivityPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_user_activities(
    user_id: core_dependencies.UuidId,
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
) -> activity_schema.ActivityPage:
    """List another user's visible activities, with the matching total.

    Answered 404 when that user does not exist, is inactive or awaits approval.
    Items are summaries: private notes and import metadata are on `GET /activities/{activity_id}`.
    """
    return activity_service.page_user_activities(
        user_id,
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
    )
