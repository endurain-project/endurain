import core.dependencies as core_dependencies


def validate_goal_id(goal_id: int):
    # Check if id higher than 0
    core_dependencies.validate_id(id=goal_id, min=0, message="Invalid goal ID")
