"""Public (unauthenticated) routes for activity laps."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity_laps.crud as activity_laps_crud
import modules.activities.activity_laps.schema as activity_laps_schema

router = APIRouter()


@router.get(
    "/activity_id/{activity_id}/all",
    response_model=list[activity_laps_schema.ActivityLapsRead] | None,
)
async def read_public_activities_laps_for_activity_all(
    activity_id: int,
    validate_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[activity_laps_schema.ActivityLapsRead] | None:
    """
    Return public laps for an activity exposed via shareable link.

    Args:
        activity_id: Activity primary key.
        validate_id: FastAPI dependency that validates the path id.
        db: Database session.

    Returns:
        List of ``ActivityLapsRead`` or ``None`` when public sharing
        is disabled, the activity is not public, or the laps are
        hidden.
    """
    return activity_laps_crud.get_public_activity_laps(activity_id, db)
