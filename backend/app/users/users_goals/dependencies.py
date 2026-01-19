"""
Goal ID validation dependency.

This module provides validation dependencies for user goal
endpoints to ensure goal IDs are valid before processing.
"""

import core.dependencies as core_dependencies


def validate_goal_id(goal_id: int) -> None:
    """
    Validate that goal_id is a positive integer.

    Args:
        goal_id: The goal ID to validate.

    Raises:
        HTTPException: If goal_id is less than 1.
    """
    core_dependencies.validate_id(id=goal_id, min=1, message="Invalid goal ID")
