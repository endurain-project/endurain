"""Public user router for unauthenticated user info access."""

from fastapi import APIRouter, Request

import core.dependencies as core_dependencies
import core.rate_limit as core_rate_limit
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

# Define the API router
router = APIRouter()


@router.get(
    "/id/{user_id}",
    response_model=users_schema.UserPublicRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.PUBLIC_READ)
def read_users_id(
    request: Request,
    user_id: core_dependencies.PositiveId,
    db: core_dependencies.DbSession,
) -> users_schema.UserPublicRead:
    """Get public user info by ID.

    Args:
        request: The incoming request, read by the rate limiter.
        user_id: The user ID to retrieve.
        db: Database session dependency.

    Returns:
        User data if found and public sharing enabled.

    Raises:
        NotFoundError: If the user does not exist or public sharing is off.
    """
    return users_service.get_public_user(user_id, db)
