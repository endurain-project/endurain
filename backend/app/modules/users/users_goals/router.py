"""User goals API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, Security, status

import core.dependencies as core_dependencies
import core.etag as core_etag
import core.idempotency as core_idempotency
import core.location as core_location
import core.pagination as core_pagination
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.users.users_goals.progress_service as user_goals_progress_service
import modules.users.users_goals.schema as user_goals_schema
import modules.users.users_goals.service as user_goals_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=user_goals_schema.UserGoalPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
def get_user_goals(
    token_user_id: auth_dependencies.CurrentUserId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
    interval: Annotated[
        user_goals_schema.Interval | None,
        Query(description="Filter by goal interval"),
    ] = None,
    activity_type: Annotated[
        user_goals_schema.GoalActivityType | None,
        Query(description="Filter by activity type"),
    ] = None,
    goal_type: Annotated[
        user_goals_schema.GoalType | None,
        Query(description="Filter by goal type"),
    ] = None,
) -> user_goals_schema.UserGoalPage:
    """Retrieve one page of goals for the authenticated user with optional filters."""
    return user_goals_service.list_goals(
        user_id=token_user_id,
        db=db,
        page=page,
        interval=interval,
        activity_type=activity_type,
        goal_type=goal_type,
    )


@router.get(
    "/results",
    response_model=user_goals_schema.UserGoalProgressPage,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.EXPENSIVE_READ)
def get_user_goals_results(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    page: core_pagination.ListPage,
    db: core_dependencies.DbSession,
) -> user_goals_schema.UserGoalProgressPage:
    """Calculate and retrieve one page of goal progress for the authenticated user."""
    return user_goals_progress_service.get_goals_progress(token_user_id, page, db)


@router.get(
    "/{goal_id}",
    response_model=user_goals_schema.UserGoalRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
def get_user_goal(
    goal_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> user_goals_schema.UserGoalRead:
    """Retrieve one of the authenticated user's goals; its ``ETag`` is the version for ``If-Match``."""
    goal = user_goals_service.get_goal(token_user_id, goal_id, db)
    core_etag.set_etag(response, goal.version)
    return goal


@router.post(
    "",
    response_model=user_goals_schema.UserGoalRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"]), core_idempotency.Idempotent],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def create_user_goal(
    request: Request,
    user_goal: user_goals_schema.UserGoalCreate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> user_goals_schema.UserGoalRead:
    """Create a new goal for the authenticated user."""
    created = user_goals_service.create_goal(token_user_id, user_goal, db)
    core_location.set_location(response, request, "get_user_goal", goal_id=created.id)
    core_etag.set_etag(response, created.version)
    return created


@router.put(
    "/{goal_id}",
    response_model=user_goals_schema.UserGoalRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def update_user_goal(
    request: Request,
    goal_id: core_dependencies.UuidId,
    user_goal: user_goals_schema.UserGoalUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
    if_match: core_dependencies.IfMatch,
) -> user_goals_schema.UserGoalRead:
    """Replace an existing goal for the authenticated user."""
    updated = user_goals_service.update_goal(token_user_id, goal_id, user_goal, db, if_match=if_match)
    core_etag.set_etag(response, updated.version)
    return updated


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["account"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_user_goal(
    request: Request,
    goal_id: core_dependencies.UuidId,
    token_user_id: auth_dependencies.CurrentUserId,
    if_match: core_dependencies.IfMatch,
    db: core_dependencies.DbSession,
) -> None:
    """Delete a goal for the authenticated user."""
    user_goals_service.delete_goal(token_user_id, goal_id, db, if_match=if_match)
