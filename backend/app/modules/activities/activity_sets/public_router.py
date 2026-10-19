"""Public (unauthenticated) routes for activity workout sets."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.service as activity_sets_service

router = APIRouter()


@router.get(
    "/sets",
    response_model=activity_sets_schema.ActivitySetsPage,
)
def list_public_activity_sets(
    activity_id: activity_dependencies.ActivityId,
    db: Annotated[Session, Depends(core_database.get_db)],
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_sets_schema.ActivitySetsPage:
    """Return one page of a publicly shared activity's sets."""
    return activity_sets_service.list_public_activity_sets(
        activity_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
