from fastapi import APIRouter, Depends, Security, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Annotated, Callable, Union
from datetime import date, datetime, timezone

import core.database as core_database
import session.security as session_security
import users.user.dependencies as users_dependencies
import activity_summaries.crud as summary_crud
import activity_summaries.schema as summary_schema

router = APIRouter()

@router.get(
    "/user/{user_id}/{view_type}",
    response_model=Union[
        summary_schema.WeeklySummaryResponse,
        summary_schema.MonthlySummaryResponse,
        summary_schema.YearlySummaryResponse,
        summary_schema.LifetimeSummaryResponse 
    ],
    summary="Get Activity Summary by Period",
    description="Retrieves aggregated activity summaries (weekly, monthly, yearly, or lifetime) for a specific user.",
)
async def read_activity_summary(
    user_id: int,
    view_type: str,
    validate_user_id: Annotated[Callable, Depends(users_dependencies.validate_user_id)],
    check_scopes: Annotated[
        Callable, Security(session_security.check_scopes, scopes=["activities:read"])
    ],
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    target_date_str: Annotated[str | None, Query(alias="date", description="Target date (YYYY-MM-DD) for week/month view. Defaults to today.")] = None,
    target_year: Annotated[int | None, Query(alias="year", description="Target year for year view. Defaults to current year.")] = None,
    activity_type: Annotated[str | None, Query(alias="type", description="Filter summary by activity type name.")] = None,
):
    if user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access summaries for this user",
        )

    today = datetime.now(timezone.utc).date()

    if view_type == "week":
        try:
            current_date = date.fromisoformat(target_date_str) if target_date_str else today
        except (ValueError, TypeError):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Use YYYY-MM-DD.")
        return summary_crud.get_weekly_summary(db=db, user_id=user_id, target_date=current_date, activity_type=activity_type)
    elif view_type == "month":
        try:
            current_date = date.fromisoformat(target_date_str) if target_date_str else today
        except (ValueError, TypeError):
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Use YYYY-MM-DD.")
        month_start_date = current_date.replace(day=1)
        return summary_crud.get_monthly_summary(db=db, user_id=user_id, target_date=month_start_date, activity_type=activity_type)
    elif view_type == "year":
        current_year = target_year if target_year else today.year
        if not (1900 <= current_year <= 2100):
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid year. Must be between 1900 and 2100.")
        return summary_crud.get_yearly_summary(db=db, user_id=user_id, year=current_year, activity_type=activity_type)
    elif view_type == "lifetime":
        return summary_crud.get_lifetime_summary(db=db, user_id=user_id, activity_type=activity_type)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid view_type. Must be 'week', 'month', 'year', or 'lifetime'.",
        )
