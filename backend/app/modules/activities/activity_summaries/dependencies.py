"""Dependencies for activity summaries endpoints."""

from fastapi import HTTPException, status

_VALID_VIEW_TYPES = {
    "week",
    "month",
    "year",
    "lifetime",
}


def validate_view_type(view_type: str) -> None:
    """
    Validate the view type path parameter.

    Args:
        view_type: The view type to validate.

    Raises:
        HTTPException: If the view type is not
            a valid option.
    """
    if view_type not in _VALID_VIEW_TYPES:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail="Invalid view type field",
        )
