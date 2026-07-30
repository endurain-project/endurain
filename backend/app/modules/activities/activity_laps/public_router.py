"""Public (unauthenticated) routes for activity laps."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as activity_laps_service

router = APIRouter()


@router.get(
    "/laps",
    response_model=activity_laps_schema.ActivityLapsPage,
)
def read_public_activities_laps_for_activity_all(
    activity_id: int,
    db: Annotated[Session, Depends(core_database.get_db)],
    page_number: Annotated[int | None, Query(ge=1)] = None,
    num_records: Annotated[int | None, Query(ge=1, le=core_pagination.MAX_NUM_RECORDS)] = None,
) -> activity_laps_schema.ActivityLapsPage:
    """
    Return one page of public laps for an activity exposed via shareable link.

    Args:
        activity_id: Activity primary key.
        db: Database session.

    Returns:
        List of ``ActivityLapsRead`` or ``None`` when public sharing
        is disabled, the activity is not public, or the laps are
        hidden.
    """
    return activity_laps_service.list_public_activity_laps(
        activity_id,
        db,
        page_number=page_number or 1,
        num_records=num_records or core_pagination.DEFAULT_CHILD_NUM_RECORDS,
    )
