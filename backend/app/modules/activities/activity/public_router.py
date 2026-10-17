"""FastAPI routes for the activities module (public, unauthenticated)."""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service

# Define the API router
router = APIRouter()


@router.get(
    "/{activity_id}",
    response_model=activity_schema.ActivityRead,
)
def read_public_activity(
    activity_id: activity_dependencies.ActivityId,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> activity_schema.ActivityRead:
    """Return a public activity by ID.

    Answers 404 when the activity does not exist *or* is not public — the two are
    deliberately indistinguishable so this unauthenticated endpoint cannot be
    used to enumerate which activity ids exist.
    """
    return activity_service.get_public_activity(activity_id, db)
