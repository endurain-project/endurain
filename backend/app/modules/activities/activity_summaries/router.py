"""FastAPI routes for activity summaries (authenticated).

Thin HTTP adapter: it validates query parameters and delegates every decision to
:mod:`service`. Mounted under ``/activities/summaries`` — a sub-resource of
activities rather than the old top-level ``/activities_summaries`` — and the
period is a query parameter, not a path segment, because ``week``/``month``/
``year``/``lifetime`` are four views of one resource, not four resources.
"""

from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_summaries.service as summary_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "",
    response_model=summary_service.SummaryResponse,
)
def read_activity_summary(
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    period: Annotated[str, Query(pattern="^(week|month|year|lifetime)$")] = "week",
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
    target_year: Annotated[
        int | None,
        Query(alias="year", description="Target year for the yearly summary. Defaults to the anchor date's year."),
    ] = None,
    activity_type: Annotated[
        str | None,
        Query(alias="type", description="Filter the summary by activity type name."),
    ] = None,
) -> summary_service.SummaryResponse:
    """Return the authenticated user's activity summary for one period."""
    return summary_service.build_summary(
        token_user_id,
        period,
        db,
        anchor=anchor_date,
        target_year=target_year,
        activity_type=activity_type,
    )
