"""FastAPI routes for activity summaries (authenticated).

Thin HTTP adapter: it validates query parameters and delegates every decision to
:mod:`activity_summary_service`. Mounted under ``/activities/summaries`` as a sub-resource
of activities, and the period is a query parameter, not a path segment, because
``week``/``month``/
``year``/``lifetime`` are four views of one resource, not four resources.
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Security

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity.summary_schema as activity_summary_schema
import modules.activities.activity.summary_service as activity_summary_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "",
    response_model=activity_summary_schema.SummaryResponse,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def read_activity_summary(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    period: Annotated[str, Query(pattern="^(week|month|year|lifetime)$")] = "week",
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
    target_year: Annotated[
        int | None,
        Query(alias="year", description="Target year for the yearly summary. Defaults to the anchor date's year."),
    ] = None,
    activity_type: Annotated[
        str | None,
        Query(alias="type", description="Filter the summary by activity type name."),
    ] = None,
) -> activity_summary_schema.SummaryResponse:
    """Return the authenticated user's activity summary for one period."""
    return activity_summary_service.build_summary(
        token_user_id,
        period,
        db,
        anchor=anchor_date,
        target_year=target_year,
        activity_type=activity_type,
    )
