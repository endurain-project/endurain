"""CRUD operations for user goals."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.users.users_goals.models as user_goals_models
import modules.users.users_goals.schema as user_goals_schema
import modules.users.users_goals.serializers as user_goals_serializers


def _flush_goal(db: Session) -> None:
    """Flush a staged goal, turning a clash with another of the user's goals into a conflict.

    The database enforces one goal per user, interval, activity type and goal type, so two concurrent
    requests cannot both succeed.

    Args:
        db: Database session holding the staged goal.

    Raises:
        ConflictError: If the user already has a goal for this activity type, interval and goal type.
    """
    try:
        db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError(
            "User already has a goal for this activity type, interval, and goal type."
        ) from err


def _select_goal(user_id: int, goal_id: int, db: Session) -> user_goals_models.UsersGoal:
    """Select one of a user's goals as an ORM row.

    Args:
        user_id: The ID of the user.
        goal_id: The ID of the goal.
        db: Database session.

    Returns:
        The goal ORM row.

    Raises:
        NotFoundError: If the user has no such goal.
    """
    stmt = select(user_goals_models.UsersGoal).where(
        user_goals_models.UsersGoal.user_id == user_id,
        user_goals_models.UsersGoal.id == goal_id,
    )
    db_goal = db.execute(stmt).scalar_one_or_none()
    if db_goal is None:
        raise core_exceptions.NotFoundError("User goal not found")

    return db_goal


def _filtered_goals(
    stmt,
    user_id: int,
    interval: user_goals_schema.Interval | None,
    activity_type: user_goals_schema.ActivityType | None,
    goal_type: user_goals_schema.GoalType | None,
):
    """Restrict a goals statement to one user's goals and the optional filters.

    Args:
        stmt: The statement to restrict.
        user_id: The ID of the user.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.

    Returns:
        The restricted statement.
    """
    stmt = stmt.where(user_goals_models.UsersGoal.user_id == user_id)
    if interval is not None:
        stmt = stmt.where(user_goals_models.UsersGoal.interval == interval.value)
    if activity_type is not None:
        stmt = stmt.where(user_goals_models.UsersGoal.activity_type == activity_type.value)
    if goal_type is not None:
        stmt = stmt.where(user_goals_models.UsersGoal.goal_type == goal_type.value)
    return stmt


def get_user_goals_by_user_id(
    user_id: int,
    db: Session,
    interval: user_goals_schema.Interval | None = None,
    activity_type: user_goals_schema.ActivityType | None = None,
    goal_type: user_goals_schema.GoalType | None = None,
) -> list[user_goals_schema.UsersGoalRead]:
    """Retrieve every goal of a user with optional filters.

    A user has at most one goal per interval, activity type and goal type, so the set is small; use
    :func:`get_user_goals_page` for a response.

    Args:
        user_id: The ID of the user.
        db: Database session.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.

    Returns:
        The goals matching the filters.
    """
    stmt = _filtered_goals(select(user_goals_models.UsersGoal), user_id, interval, activity_type, goal_type)
    return [user_goals_serializers.to_read_schema(goal) for goal in db.execute(stmt).scalars().all()]


def get_user_goals_page(
    user_id: int,
    db: Session,
    interval: user_goals_schema.Interval | None = None,
    activity_type: user_goals_schema.ActivityType | None = None,
    goal_type: user_goals_schema.GoalType | None = None,
    *,
    limit: int,
    offset: int,
) -> list[user_goals_schema.UsersGoalRead]:
    """Retrieve one window of a user's goals, in id order.

    Args:
        user_id: The ID of the user.
        db: Database session.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.
        limit: The most goals to return.
        offset: How many matching goals to skip.

    Returns:
        The goals in the window.
    """
    stmt = (
        _filtered_goals(select(user_goals_models.UsersGoal), user_id, interval, activity_type, goal_type)
        .order_by(user_goals_models.UsersGoal.id)
        .limit(limit)
        .offset(offset)
    )
    return [user_goals_serializers.to_read_schema(goal) for goal in db.execute(stmt).scalars().all()]


def count_user_goals(
    user_id: int,
    db: Session,
    interval: user_goals_schema.Interval | None = None,
    activity_type: user_goals_schema.ActivityType | None = None,
    goal_type: user_goals_schema.GoalType | None = None,
) -> int:
    """Count a user's goals matching the optional filters.

    Args:
        user_id: The ID of the user.
        db: Database session.
        interval: Optional filter by goal interval.
        activity_type: Optional filter by activity type.
        goal_type: Optional filter by goal type.

    Returns:
        The number of matching goals.
    """
    stmt = _filtered_goals(
        select(func.count(user_goals_models.UsersGoal.id)), user_id, interval, activity_type, goal_type
    )
    return db.execute(stmt).scalar_one()


def create_user_goal(
    user_id: int,
    user_goal: user_goals_schema.UsersGoalCreate,
    db: Session,
) -> user_goals_schema.UsersGoalRead:
    """Stage a new user goal (flushed, not committed).

    Args:
        user_id: The ID of the user.
        user_goal: Goal data to create.
        db: Database session.

    Returns:
        The created goal.

    Raises:
        ConflictError: If the user already has a goal for this activity type, interval and goal type.
    """
    db_goal = user_goals_models.UsersGoal(
        user_id=user_id,
        interval=user_goal.interval,
        activity_type=user_goal.activity_type,
        goal_type=user_goal.goal_type,
        goal_calories=user_goal.goal_calories,
        goal_activities_number=user_goal.goal_activities_number,
        goal_distance=user_goal.goal_distance,
        goal_elevation=user_goal.goal_elevation,
        goal_duration=user_goal.goal_duration,
    )
    db.add(db_goal)
    _flush_goal(db)
    db.refresh(db_goal)

    return user_goals_serializers.to_read_schema(db_goal)


def update_user_goal(
    user_id: int,
    goal_id: int,
    user_goal: user_goals_schema.UsersGoalUpdate,
    db: Session,
    *,
    if_match: str,
) -> user_goals_schema.UsersGoalRead:
    """Stage an update of a user's goal (flushed, not committed).

    Args:
        user_id: The ID of the user who owns the goal.
        goal_id: The goal to update.
        user_goal: Schema with the goal's new values.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The updated goal.

    Raises:
        NotFoundError: If the user has no such goal.
        ConflictError: If the new values match another of the user's goals.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    db_goal = _select_goal(user_id, goal_id, db)
    core_etag.require_if_match(if_match, db_goal.version, "goal")

    # The update is the whole goal: a target the body leaves out is cleared, not kept from the old goal.
    for field, value in user_goal.model_dump().items():
        setattr(db_goal, field, value)

    _flush_goal(db)
    db.refresh(db_goal)

    return user_goals_serializers.to_read_schema(db_goal)


def delete_user_goal(user_id: int, goal_id: int, db: Session, *, if_match: str) -> None:
    """Stage the deletion of a user's goal (flushed, not committed).

    Args:
        user_id: The ID of the user who owns the goal.
        goal_id: The ID of the goal to delete.
        db: Database session.
        if_match: The ``If-Match`` precondition, checked against the very row that is deleted.

    Raises:
        NotFoundError: If the user has no such goal.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    db_goal = _select_goal(user_id, goal_id, db)
    core_etag.require_if_match(if_match, db_goal.version, "goal")
    db.delete(db_goal)
    db.flush()


def user_goal_exists(user_id: int, goal_id: int, db: Session) -> bool:
    """Report whether a user has a goal.

    Args:
        user_id: The ID of the user.
        goal_id: The ID of the goal.
        db: Database session.

    Returns:
        True when the user has such a goal.
    """
    stmt = select(
        select(user_goals_models.UsersGoal.id)
        .where(user_goals_models.UsersGoal.user_id == user_id, user_goals_models.UsersGoal.id == goal_id)
        .exists()
    )
    return bool(db.execute(stmt).scalar())
