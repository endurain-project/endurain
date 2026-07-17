from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity.dependencies as activities_dependencies
import modules.activities.activity_sets.crud as activity_sets_crud
import modules.activities.activity_sets.schema as activity_sets_schema

# Define the API router
router = APIRouter()


@router.get(
    "/activity_id/{activity_id}/all",
    response_model=list[activity_sets_schema.ActivitySetsRead] | None,
)
def read_public_activities_sets_for_activity_all(
    activity_id: int,
    validate_id: Annotated[Callable, Depends(activities_dependencies.validate_activity_id)],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activity sets from the database and return them
    return activity_sets_crud.get_public_activity_sets(activity_id, db)
