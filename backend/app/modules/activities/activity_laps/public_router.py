"""Public (unauthenticated) routes for activity laps."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as activity_laps_service

router = APIRouter()


@router.get(
    "/laps",
    response_model=activity_laps_schema.ActivityLapsPage,
)
def list_public_activity_laps(
    activity_id: activity_dependencies.ActivityId,
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_laps_schema.ActivityLapsPage:
    """Return one page of public laps for an activity exposed via shareable link."""
    return activity_laps_service.list_public_activity_laps(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
