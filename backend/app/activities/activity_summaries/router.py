from fastapi import APIRouter, Depends, Security, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Annotated, Callable, Union
from datetime import date, datetime, timezone

import core.database as core_database
import auth.security as auth_security
import activities.activity.dependencies as activities_dependencies
import activities.activity_summaries.crud as activities_summary_crud
import activities.activity_summaries.schema as activities_summary_schema
import activities.activity_summaries.dependencies as activities_summary_dependencies

router = APIRouter()


@router.get(
    "/{view_type}",
    response_model=Union[
        activities_summary_schema.WeeklySummaryResponse,
        activities_summary_schema.MonthlySummaryResponse,
        activities_summary_schema.YearlySummaryResponse,
        activities_summary_schema.LifetimeSummaryResponse,
    ],
)
async def read_activity_summary(
    view_type: str,
    validate_view_type: Annotated[
        Callable, Depends(activities_summary_dependencies.validate_view_type)
    ],
    _check_scopes: Annotated[
        Callable, Security(auth_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    # Added dependencies for optional query parameters
    validate_activity_type: Annotated[
        Callable, Depends(activities_dependencies.validate_activity_type)
    ],
    target_date_str: Annotated[
        str | None,
        Query(
            alias="date",
            description="Target date (YYYY-MM-DD) for week/month view. Defaults to today.",
        ),
    ] = None,
    target_year: Annotated[
        int | None,
        Query(
            alias="year",
            description="Target year for year view. Defaults to current year.",
        ),
    ] = None,
    activity_type: Annotated[
        str | None,
        Query(alias="type", description="Filter summary by activity type name."),
    ] = None,
):
    today = datetime.now(timezone.utc).date()

    if view_type == "week":
        try:
            current_date = (
                date.fromisoformat(target_date_str) if target_date_str else today
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD.",
            )
        return activities_summary_crud.get_weekly_summary(
            db=db,
            user_id=token_user_id,
            target_date=current_date,
            activity_type=activity_type,
        )
    elif view_type == "month":
        try:
            current_date = (
                date.fromisoformat(target_date_str) if target_date_str else today
            )
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use YYYY-MM-DD.",
            )
        month_start_date = current_date.replace(day=1)
        return activities_summary_crud.get_monthly_summary(
            db=db,
            user_id=token_user_id,
            target_date=month_start_date,
            activity_type=activity_type,
        )
    elif view_type == "year":
        current_year = target_year if target_year else today.year
        if not (1900 <= current_year <= today.year):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid year. Must be between 1900 and {today.year}.",
            )
        return activities_summary_crud.get_yearly_summary(
            db=db, user_id=token_user_id, year=current_year, activity_type=activity_type
        )
    else:
        return activities_summary_crud.get_lifetime_summary(
            db=db, user_id=token_user_id, activity_type=activity_type
        )
