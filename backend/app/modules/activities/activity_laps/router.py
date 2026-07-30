"""Authenticated routes for activity laps."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Security
from sqlalchemy.orm import Session

import core.database as core_database
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as activity_laps_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/laps",
    response_model=list[activity_laps_schema.ActivityLapsRead],
)
def read_activities_laps_for_activity_all(
    activity_id: int,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["activities:read"]),
    ],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    db: Annotated[Session, Depends(core_database.get_db)],
) -> list[activity_laps_schema.ActivityLapsRead]:
    """
    Return all laps for the given activity visible to the caller.

    Args:
        activity_id: Activity primary key.
        _check_scopes: FastAPI security dependency enforcing scopes.
        token_user_id: Authenticated user id derived from the access
            token.
        db: Database session.

    Returns:
        List of ``ActivityLapsRead`` or ``None`` if the activity is
        hidden from the caller or has no laps.
    """
    return activity_laps_service.list_activity_laps(activity_id, token_user_id, db)
