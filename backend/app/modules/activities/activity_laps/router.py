"""Authenticated routes for activity laps."""

from typing import Annotated

from fastapi import APIRouter, Depends, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_laps.schema as activity_laps_schema
import modules.activities.activity_laps.service as activity_laps_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/laps",
    response_model=activity_laps_schema.ActivityLapsPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_laps(
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_laps_schema.ActivityLapsPage:
    """Return one page of the given activity's laps, with the matching total."""
    return activity_laps_service.list_activity_laps(
        activity_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
