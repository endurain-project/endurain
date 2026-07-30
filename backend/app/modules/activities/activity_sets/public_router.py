"""Public (unauthenticated) routes for activity workout sets."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.service as activity_sets_service

router = APIRouter()


@router.get(
    "/sets",
    response_model=activity_sets_schema.ActivitySetsPage,
)
def read_public_activities_sets_for_activity_all(
    activity_id: int,
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
) -> activity_sets_schema.ActivitySetsPage:
    """Return one page of a publicly shared activity's sets.

    Args:
        activity_id: Activity primary key.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size, capped so one request cannot ask for an
            unbounded number of rows.

    Returns:
        The page envelope. Empty when public sharing is disabled, the activity is
        not public, or the sets are hidden.
    """
    return activity_sets_service.list_public_activity_sets(
        activity_id,
        db,
        page_number=page_number or 1,
        num_records=num_records or core_pagination.DEFAULT_CHILD_NUM_RECORDS,
    )
