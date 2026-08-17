"""Authenticated routes for activity laps."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
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
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_laps_schema.ActivityLapsPage:
    """
    Return one page of the given activity's laps, with the matching total.

    Args:
        activity_id: Activity primary key.
        _check_scopes: FastAPI security dependency enforcing scopes.
        token_user_id: Authenticated user id derived from the access
            token.
        db: Database session.
        page: Resolved paging window, capped so one request cannot ask for
            an unbounded number of rows.

    Returns:
        The page envelope. Empty when the activity is hidden from the caller or
        has no laps.
    """
    return activity_laps_service.list_activity_laps(
        activity_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
