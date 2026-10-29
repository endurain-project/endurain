"""Application logic for user goals.

Decides who may edit which goal and owns the commit for the user's own requests. The
progress calculation is :mod:`modules.users.users_goals.progress_service`; what other
modules may consume lives in :mod:`modules.users.users_goals.integration_service`.
"""

from sqlalchemy.orm import Session

import core.etag as core_etag
import core.logger as core_logger
import core.pagination as core_pagination
import modules.users.users_goals.crud as user_goals_crud
import modules.users.users_goals.schema as user_goals_schema

logger = core_logger.get_logger(__name__)


def list_goals(
    user_id: int,
    page: core_pagination.PageParams,
    db: Session,
    interval: user_goals_schema.Interval | None = None,
    activity_type: user_goals_schema.ActivityType | None = None,
    goal_type: user_goals_schema.GoalType | None = None,
) -> user_goals_schema.UsersGoalPage:
    """List one page of a user's goals with optional filters.

    Args:
        user_id: The user whose goals to list.
        page: The requested window.
        db: Database session.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.

    Returns:
        The page of goals matching the filters.
    """
    goals = user_goals_crud.get_user_goals_page(
        user_id,
        db,
        interval,
        activity_type,
        goal_type,
        limit=page.num_records,
        offset=(page.page_number - 1) * page.num_records,
    )
    total = user_goals_crud.count_user_goals(user_id, db, interval, activity_type, goal_type)
    return user_goals_schema.UsersGoalPage.build(goals, total, page.page_number, page.num_records)


def create_goal(
    user_id: int,
    user_goal: user_goals_schema.UsersGoalCreate,
    db: Session,
) -> user_goals_schema.UsersGoalRead:
    """Create a goal for a user and commit.

    Args:
        user_id: The user the goal belongs to.
        user_goal: Goal data to create.
        db: Database session.

    Returns:
        The created goal.

    Raises:
        ConflictError: If the user already has a goal for this activity type, interval and goal type.
    """
    created = user_goals_crud.create_user_goal(user_id, user_goal, db)
    db.commit()
    logger.debug("User goal created", extra=core_logger.context(user_id=user_id, goal_id=created.id))
    return created


def update_goal(
    user_id: int,
    goal_id: int,
    user_goal: user_goals_schema.UsersGoalUpdate,
    db: Session,
    *,
    if_match: str,
) -> user_goals_schema.UsersGoalRead:
    """Replace a user's goal and commit.

    Args:
        user_id: The user who owns the goal.
        goal_id: The goal to replace.
        user_goal: The goal's new values.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated goal.

    Raises:
        NotFoundError: If the user has no such goal.
        PreconditionFailedError: If the goal changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db,
        "goal",
        lambda: user_goals_crud.user_goal_exists(user_id, goal_id, db),
        "User goal not found",
    ):
        updated = user_goals_crud.update_user_goal(user_id, goal_id, user_goal, db, if_match=if_match)
        db.commit()
    logger.debug("User goal updated", extra=core_logger.context(user_id=user_id, goal_id=updated.id))
    return updated


def delete_goal(user_id: int, goal_id: int, db: Session, *, if_match: str) -> None:
    """Delete a user's goal and commit.

    Args:
        user_id: The user who owns the goal.
        goal_id: The goal to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Raises:
        NotFoundError: If the user has no such goal.
        PreconditionFailedError: If the goal changed since the client read it.
    """
    with core_etag.refuse_stale_write(
        db,
        "goal",
        lambda: user_goals_crud.user_goal_exists(user_id, goal_id, db),
        "User goal not found",
    ):
        user_goals_crud.delete_user_goal(user_id, goal_id, db, if_match=if_match)
        db.commit()
    logger.debug("User goal deleted", extra=core_logger.context(user_id=user_id, goal_id=goal_id))
