"""Routes for signed-in users' views of another user's profile."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Security

import core.dependencies as core_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.users.users_profile.schema as profile_schema
import modules.users.users_profile.service as profile_service

router = APIRouter()


@router.get(
    "/id/{user_id}/overview",
    response_model=profile_schema.UserProfileOverviewRead,
    dependencies=[
        Security(
            auth_dependencies.check_scopes,
            scopes=["users:read", "activities:read", "followers:read"],
        )
    ],
)
def read_user_profile_overview(
    user_id: core_dependencies.PositiveId,
    requester_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    anchor_date: Annotated[
        date | None,
        Query(
            alias="date",
            description="The viewer's local calendar date for current-week and current-month values.",
        ),
    ] = None,
) -> profile_schema.UserProfileOverviewRead:
    """Return the public profile and summary values the profile page displays."""
    return profile_service.get_user_profile_overview(
        user_id,
        requester_user_id,
        db,
        anchor_date=anchor_date,
    )
