"""Router for activity summary endpoints."""

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

import core.database as core_database
import modules.activities.activity_summaries.crud as summary_crud
import modules.activities.activity_summaries.dependencies as summary_deps
import modules.activities.activity_summaries.schema as summary_schema
import modules.auth.dependencies as auth_dependencies
import modules.users.users.utils as users_utils

router = APIRouter()

# Widest real-world UTC offset (Pacific/Kiritimati, +14:00). The server cannot
# know the caller's timezone, so any "is this year plausible?" check has to be
# tolerant by at least this much or it rejects the caller's genuinely current
# year around New Year.
_MAX_UTC_OFFSET = timedelta(hours=14)


def _latest_plausible_year() -> int:
    """Return the highest year any caller could currently be in.

    ``datetime.now(UTC).year`` is the *server's* year. For a user in UTC+13 that
    is still the previous year for the first 13 hours of 1 January, so validating
    against it rejected the year they are actually living in. Widening by the
    maximum real UTC offset keeps the guard (it still rejects far-future years)
    without depending on a timezone the request never carries.
    """
    return (datetime.now(UTC) + _MAX_UTC_OFFSET).year


def _parse_target_date(
    target_date_str: str | None,
    fallback: date,
) -> date:
    """
    Parse a date string or return fallback.

    Args:
        target_date_str: ISO date string or None.
        fallback: Default date when string is None.

    Returns:
        Parsed date.

    Raises:
        HTTPException: If format is invalid.
    """
    if not target_date_str:
        return fallback
    try:
        return date.fromisoformat(target_date_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=(status.HTTP_400_BAD_REQUEST),
            detail=("Invalid date format. Use YYYY-MM-DD."),
        ) from None


@router.get(
    "/{view_type}",
    response_model=(
        summary_schema.WeeklySummaryResponse
        | summary_schema.MonthlySummaryResponse
        | summary_schema.YearlySummaryResponse
        | summary_schema.LifetimeSummaryResponse
    ),
)
def read_activity_summary(
    view_type: str,
    _validate_view_type: Annotated[
        Callable,
        Depends(summary_deps.validate_view_type),
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
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    target_date_str: Annotated[
        str | None,
        Query(
            alias="date",
            description=("Target date (YYYY-MM-DD) for week/month view. Defaults to today."),
        ),
    ] = None,
    target_year: Annotated[
        int | None,
        Query(
            alias="year",
            description=("Target year for year view. Defaults to current year."),
        ),
    ] = None,
    activity_type: Annotated[
        str | None,
        Query(
            alias="type",
            description=("Filter summary by activity type name."),
        ),
    ] = None,
) -> (
    summary_schema.WeeklySummaryResponse
    | summary_schema.MonthlySummaryResponse
    | summary_schema.YearlySummaryResponse
    | summary_schema.LifetimeSummaryResponse
):
    """
    Read activity summary for a given view type.

    Args:
        view_type: One of week, month, year,
            lifetime.
        validate_view_type: Dependency that
            validates view_type.
        _check_scopes: Dependency that checks
            required scopes.
        token_user_id: Authenticated user ID.
        db: Database session.
        target_date_str: Optional ISO date for
            week/month views.
        target_year: Optional year for year view.
        activity_type: Optional activity type name
            filter.

    Returns:
        Summary response matching the view type.

    Raises:
        HTTPException: If date/year is invalid.
    """
    # Server-side fallback anchor for callers that omit ``date``/``year``. The
    # web client always sends its own local date (the request carries no
    # timezone, so the server cannot derive it); when it does not, the caller's
    # configured timezone is the same frame of reference it would have sent.
    today = users_utils.user_local_today(token_user_id, db)

    if view_type == "week":
        current_date = _parse_target_date(target_date_str, today)
        return summary_crud.get_weekly_summary(
            db=db,
            user_id=token_user_id,
            target_date=current_date,
            activity_type=activity_type,
        )

    if view_type == "month":
        current_date = _parse_target_date(target_date_str, today)
        return summary_crud.get_monthly_summary(
            db=db,
            user_id=token_user_id,
            target_date=current_date.replace(day=1),
            activity_type=activity_type,
        )

    if view_type == "year":
        max_year = _latest_plausible_year()
        current_year = target_year if target_year else today.year
        if not (1900 <= current_year <= max_year):
            raise HTTPException(
                status_code=(status.HTTP_400_BAD_REQUEST),
                detail=(f"Invalid year. Must be between 1900 and {max_year}."),
            )
        return summary_crud.get_yearly_summary(
            db=db,
            user_id=token_user_id,
            year=current_year,
            activity_type=activity_type,
        )

    return summary_crud.get_lifetime_summary(
        db=db,
        user_id=token_user_id,
        activity_type=activity_type,
    )
