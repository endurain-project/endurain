"""Authenticated routes for activity laps."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Security
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as activity_laps_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/laps",
    response_model=activity_laps_schema.ActivityLapsPage,
)
def read_activities_laps_for_activity_all(
    activity_id: int,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:read"]),
    ],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
) -> activity_laps_schema.ActivityLapsPage:
    """
    Return one page of the given activity's laps, with the matching total.

    Args:
        activity_id: Activity primary key.
        _check_scopes: FastAPI security dependency enforcing scopes.
        token_user_id: Authenticated user id derived from the access
            token.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size, capped so one request cannot ask for an
            unbounded number of rows.

    Returns:
        The page envelope. Empty when the activity is hidden from the caller or
        has no laps.
    """
    return activity_laps_service.list_activity_laps(
        activity_id,
        token_user_id,
        db,
        page_number=page_number or 1,
        num_records=num_records or core_pagination.DEFAULT_CHILD_NUM_RECORDS,
    )
