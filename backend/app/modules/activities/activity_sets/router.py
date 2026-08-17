"""Authenticated routes for activity workout sets."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.service as activity_sets_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/sets",
    response_model=activity_sets_schema.ActivitySetsPage,
)
def read_activities_sets_for_activity_all(
    activity_id: int,
    _check_scopes: Annotated[Callable, Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_sets_schema.ActivitySetsPage:
    """Return one page of the activity's sets, with the matching total.

    Args:
        activity_id: Activity primary key.
        _check_scopes: FastAPI security dependency enforcing scopes.
        token_user_id: Authenticated user id derived from the access token.
        db: Database session.
        page: Resolved paging window, capped so one request cannot ask for
            an unbounded number of rows.

    Returns:
        The page envelope. Empty when the activity is hidden from the caller or
        has no sets.
    """
    return activity_sets_service.list_activity_sets(
        activity_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
