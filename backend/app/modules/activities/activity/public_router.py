"""FastAPI routes for the activities module (public, unauthenticated)."""

from fastapi import (
    APIRouter,
    Request,
)

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.activities.activity.dependencies as activity_dependencies
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service

# Define the API router
router = APIRouter()


@router.get(
    "/{activity_id}",
    response_model=activity_schema.ActivityRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_public_activity(
    request: Request,
    activity_id: activity_dependencies.ActivityId,
    db: core_dependencies.DbSession,
) -> activity_schema.ActivityRead:
    """Return a public activity by ID.

    Answers 404 when the activity does not exist *or* is not public — the two are
    deliberately indistinguishable so this unauthenticated endpoint cannot be
    used to enumerate which activity ids exist.
    """
    return activity_service.get_public_activity(activity_id, db)
