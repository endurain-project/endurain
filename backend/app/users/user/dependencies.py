import core.dependencies as core_dependencies


def validate_user_id(user_id: int) -> None:
    """
    Validate that user ID is positive.

    Args:
        user_id: User ID to validate.

    Returns:
        None

    Raises:
        HTTPException: 400 if user ID is invalid (≤ 0).
    """
    core_dependencies.validate_id(id=user_id, min=0, message="Invalid user ID")


def validate_target_user_id(target_user_id: int) -> None:
    """
    Validate that target user ID is positive.

    Args:
        target_user_id: Target user ID to validate.

    Returns:
        None

    Raises:
        HTTPException: 400 if target user ID is invalid (≤ 0).
    """
    core_dependencies.validate_id(
        id=target_user_id, min=0, message="Invalid target user ID"
    )
