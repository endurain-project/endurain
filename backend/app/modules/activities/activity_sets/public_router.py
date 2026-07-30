from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.service as activity_sets_service

# Define the API router
router = APIRouter()


@router.get(
    "/sets",
    response_model=list[activity_sets_schema.ActivitySetsRead],
)
def read_public_activities_sets_for_activity_all(
    activity_id: int,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the activity sets from the database and return them
    return activity_sets_service.list_public_activity_sets(activity_id, db)
