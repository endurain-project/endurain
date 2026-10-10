"""FastAPI routes for the activities module (public, unauthenticated)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity.schema as activities_schema
import modules.activities.activity.service as activities_service

# Define the API router
router = APIRouter()


@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity,
)
def read_public_activities_activity_from_id(
    activity_id: int,
    _validate_activity_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Return a public activity by ID.

    Answers 404 when the activity does not exist *or* is not public — the two are
    deliberately indistinguishable so this unauthenticated endpoint cannot be
    used to enumerate which activity ids exist. It previously returned
    ``200 null``, which is neither a resource nor an error.
    """
    return activities_service.get_public_activity(activity_id, db)
