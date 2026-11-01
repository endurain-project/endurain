"""The user goals surface other modules may call.

Writes stage; the caller owns the commit.
"""

from sqlalchemy.orm import Session

import modules.users.users_goals.crud as user_goals_crud
import modules.users.users_goals.schema as user_goals_schema


def list_goals(user_id: int, db: Session) -> list[user_goals_schema.UsersGoalRead]:
    """List all of a user's goals.

    Args:
        user_id: The user whose goals to list.
        db: Database session.

    Returns:
        The user's goals.
    """
    return user_goals_crud.get_user_goals_by_user_id(user_id, db)


def create_goal(
    user_id: int,
    user_goal: user_goals_schema.UsersGoalCreate,
    db: Session,
) -> user_goals_schema.UsersGoalRead:
    """Stage a new goal for a user.

    Args:
        user_id: The user the goal belongs to.
        user_goal: Goal data to create.
        db: Database session.

    Returns:
        The created goal.

    Raises:
        ConflictError: If the user already has a goal for this activity type, interval and goal type.
    """
    return user_goals_crud.create_user_goal(user_id, user_goal, db)
