from fastapi import HTTPException, status, Query

import core.dependencies as core_dependencies
from activities.activity.utils import ACTIVITY_ID_TO_NAME


def validate_activity_id(activity_id: int):
    """
    Validates the provided activity ID.

    This function ensures that the given activity ID is greater than or equal to 0.
    If the validation fails, an exception is raised with the specified error message.

    Args:
        activity_id (int): The ID of the activity to validate.

    Raises:
        ValueError: If the activity ID is less than 0.
    """
    # Check if id higher than 0
    core_dependencies.validate_id(id=activity_id, min=0, message="Invalid activity ID")


def validate_week_number(week_number: int):
    """
    Validates the provided week number.

    Args:
        week_number (int): The week number to validate. Must be an integer between 0 and 52.

    Raises:
        ValueError: If the week number is not within the valid range or is of an incorrect type.
    """
    # check if week_number is between 0 and 52
    core_dependencies.validate_type(
        type=week_number, min=0, max=52, message="Invalid week number"
    )


def validate_visibility(visibility: int):
    """
    Validates the visibility value to ensure it is within the allowed range.

    Args:
        visibility (int): The visibility value to validate. Must be an integer 
                          between 0 and 2 (inclusive).

    Raises:
        ValueError: If the visibility value is not within the range [0, 2].
    """
    # check if visibility is between 0 and 2
    core_dependencies.validate_type(
        type=visibility, min=0, max=2, message="Invalid visibility"
    )


def validate_activity_type(activity_type: int | None = Query(None)):
    """
    Validates the provided activity type against a predefined mapping of valid activity types.

    Args:
        activity_type (int | None): The activity type to validate. Defaults to None.

    Raises:
        HTTPException: If the provided activity type is not in the predefined mapping 
                       and is not None, an HTTP 422 Unprocessable Entity exception is raised.

    """
    if activity_type not in ACTIVITY_ID_TO_NAME and activity_type is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid activity type",
        )


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
            - "start_time"
            - "duration"
            - "distance"
            - "pace"
            - "calories"
            - "elevation"
            - "avreage_hr"
            or `None`.

    Raises:
        HTTPException: If `sort_by` is not `None` and is not one of the allowed values,
            an HTTP 422 Unprocessable Entity exception is raised with the detail
            "Invalid sort by field".
    """
    # check if sort_by is one of the following or not None
    # sort_by can be "type", "name", "location", "start_time", "duration", "distance",
    if (
        sort_by
        not in [
            "type",
            "name",
            "location",
            "start_time",
            "duration",
            "distance",
            "pace",
            "calories",
            "elevation",
            "average_hr",
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
