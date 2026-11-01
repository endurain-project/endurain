"""ORM↔schema transformation for user goals.

``crud`` calls these at its edges so ORM rows never leave the persistence layer.
"""

import modules.users.users_goals.models as user_goals_models
import modules.users.users_goals.schema as user_goals_schema


def to_read_schema(goal: user_goals_models.UsersGoal) -> user_goals_schema.UsersGoalRead:
    """Transform a user goal ORM row into its read schema.

    Args:
        goal: The user goal ORM instance.

    Returns:
        The user goal as a schema.
    """
    return user_goals_schema.UsersGoalRead.model_validate(goal)
