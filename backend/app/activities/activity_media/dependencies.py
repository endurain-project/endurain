import core.dependencies as core_dependencies


def validate_media_id(media_id: int):
    """
    Validates the provided media ID.

    This function ensures that the given media ID is greater than or equal to 0.
    If the validation fails, an exception is raised with the specified error message.

    Args:
        media_id (int): The ID of the media to validate.

    Raises:
        ValueError: If the media ID is less than 0.
    """
    # Check if id higher than 0
    core_dependencies.validate_id(id=media_id, min=0, message="Invalid media ID")
