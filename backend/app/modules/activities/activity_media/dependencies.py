"""
Media ID validation dependency.

This module provides validation dependencies for activity media
endpoints to ensure media IDs are valid before processing.
"""

import core.dependencies as core_dependencies


def validate_media_id(media_id: int) -> None:
    """
    Validate that media_id is a non-negative integer.

    Args:
        media_id: The activity media ID to validate.

    Raises:
        HTTPException: If media_id is less than 0.
    """
    core_dependencies.validate_id(identifier=media_id, min_value=0, message="Invalid media ID")
