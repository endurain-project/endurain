"""Authenticated routes for activity workout sets."""

from typing import Annotated

from fastapi import APIRouter, Depends, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity_sets.schema as activity_sets_schema
import modules.activities.activity_sets.service as activity_sets_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/sets",
    response_model=activity_sets_schema.ActivitySetsPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_activity_sets(
    activity_id: activity_dependencies.ActivityId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: Annotated[core_pagination.PageParams, Depends(core_pagination.child_page_params)],
) -> activity_sets_schema.ActivitySetsPage:
    """Return one page of the activity's sets, with the matching total."""
    return activity_sets_service.list_activity_sets(
        activity_id,
        token_user_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
