import core.dependencies as core_dependencies


def validate_notification_id(notification_id: int):
    """
    Validates the provided notification ID.

    This function ensures that the given notification ID is greater than or equal to 0.
    If the validation fails, an exception is raised with the specified error message.

    Args:
        notification_id (int): The ID of the notification to validate.

    Raises:
        ValueError: If the notification ID is less than 0.
    """
    # Check if id higher than 0
    core_dependencies.validate_id(
        id=notification_id, min=0, message="Invalid notification ID"
    )
