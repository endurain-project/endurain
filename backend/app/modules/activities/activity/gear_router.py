"""FastAPI routes for the activities recorded with a gear (authenticated), served under ``/gears``."""

from fastapi import APIRouter, Security

import core.dependencies as core_dependencies
import core.pagination as core_pagination
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
import modules.auth.dependencies as auth_dependencies

router = APIRouter()


@router.get(
    "/{gear_id}/activities",
    response_model=activity_schema.ActivityPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["activities:read"])],
)
def list_gear_activities(
    gear_id: core_dependencies.PositiveId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    page: core_pagination.ListPage,
) -> activity_schema.ActivityPage:
    """List the authenticated user's activities for a gear, with the matching total."""
    return activity_service.page_gear_activities(
        token_user_id,
        gear_id,
        db,
        page_number=page.page_number,
        num_records=page.num_records,
    )
