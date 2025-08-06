from fastapi import HTTPException, status, Query

import core.dependencies as core_dependencies

def validate_segment_id(segment_id: int):
    """
    Validates the provided segment ID.

    This function ensures that the given segment ID is greater than or equal to 0.
    If the validation fails, an exception is raised with the specified error message.

    Args:
        activity_id (int): The ID of the segment to validate.

    Raises:
        ValueError: If the segment ID is less than 0.
    """
    # Check if id higher than 0
    core_dependencies.validate_id(id=segment_id, min=0, message="Invalid segment ID")

def validate_sort_by(sort_by: str | None = Query(None)):
    """
    Validates the `sort_by` query parameter to ensure it is either `None` or one of the
    allowed sorting fields.

    Args:
        sort_by (str | None): The sorting field provided as a query parameter.
            It can be one of the following values:
            - "type"
            - "name"
            - "location"
            - "num_activities"
            - "most_recent_activity"
            or `None`.

    Raises:
        HTTPException: If `sort_by` is not `None` and is not one of the allowed values,
            an HTTP 422 Unprocessable Entity exception is raised with the detail
            "Invalid sort by field".
    """
    # check if sort_by is one of the following or not None
    # sort_by can be "type", "name", "location", "num_activities", "most_recent_activity"
    if (
        sort_by
        not in [
            "type",
            "name",
            "location",
            "num_activities",
            "most_recent_activity",
        ]
        and sort_by is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid sort by field",
        )

def validate_sort_order(sort_order: str | None = Query(None)):
    """
    Validates the provided sort order parameter.

    Args:
        sort_order (str | None): The sort order to validate. It can be "asc", "desc", or None.

    Raises:
        HTTPException: If the sort_order is not "asc", "desc", or None, an HTTP 422 Unprocessable Entity error is raised.
    """
    # check if sort_order is one of the following or not None
    # sort_order can be "asc", "desc" or None
    if sort_order not in ["asc", "desc"] and sort_order is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid sort order",
        )
