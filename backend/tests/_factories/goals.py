"""User goals as the application stores them, for tests on the real database."""

import uuid

from sqlalchemy.orm import Session

import modules.users.users_goals.crud as goals_crud
import modules.users.users_goals.schema as goals_schema


def make_goal(db: Session, user_id: uuid.UUID, **overrides: object) -> goals_schema.UserGoalRead:
    """Stage a goal through the module's create function (flushed, not committed).

    A user has one goal per activity type, interval and goal type, so a test that stages several for one user varies
    one of them.

    Args:
        db: Database session.
        user_id: The goal's owner.
        **overrides: Field values of :class:`~modules.users.users_goals.schema.UserGoalCreate`, which replace the
            defaults of a weekly 50 km running goal.

    Returns:
        The staged goal.
    """
    values: dict[str, object] = {
        "interval": "weekly",
        "activity_type": "run",
        "goal_type": "distance",
        "goal_distance": 50000,
    }
    values.update(overrides)
    return goals_crud.create_user_goal(user_id, goals_schema.UserGoalCreate.model_validate(values), db)
