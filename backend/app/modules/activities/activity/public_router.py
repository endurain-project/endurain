"""FastAPI routes for the activities module (public, unauthenticated)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.crud as activities_crud
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity.schema as activities_schema

# Define the API router
router = APIRouter()


@router.get(
    "/{activity_id}",
    response_model=activities_schema.Activity | None,
)
def read_public_activities_activity_from_id(
    activity_id: int,
    _validate_activity_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Return a public activity by ID, or None if not found/not public."""
    return activities_crud.get_activity_by_id_if_is_public(activity_id, db)
