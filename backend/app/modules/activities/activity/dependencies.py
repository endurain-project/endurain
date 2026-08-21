from fastapi import HTTPException, Query, status

import core.dependencies as core_dependencies
import core.logger as core_logger
from modules.activities.activity.constants import (
    ACTIVITY_ID_TO_NAME,
    ACTIVITY_SORT_FIELDS,
    ACTIVITY_SORT_ORDERS,
)

logger = core_logger.get_logger(__name__)


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
    # Activity primary keys are >= 0; align with schema field constraint.
    core_dependencies.validate_id(identifier=activity_id, min_value=0, message="Invalid activity ID")


def validate_week_number(week_number: int):
    """
    Validates the provided week number.

    Args:
        week_number (int): The week number to validate. Must be an integer between 0 and 52.

    Raises:
        ValueError: If the week number is not within the valid range or is of an incorrect type.
    """
    # check if week_number is between 0 and 52
    core_dependencies.validate_type(type_value=week_number, min_value=0, max_value=52, message="Invalid week number")


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
    core_dependencies.validate_type(type_value=visibility, min_value=0, max_value=2, message="Invalid visibility")


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
        logger.debug(
            "Rejected activity list request with an unknown activity type",
            extra=core_logger.context(activity_type=activity_type),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid activity type",
        )


def validate_sort_by(sort_by: str | None = Query(None)):
    """
    Validates the `sort_by` query parameter to ensure it is either `None` or one of the
    allowed sorting fields (:data:`~modules.activities.activity.constants.ACTIVITY_SORT_FIELDS`).

    Args:
        sort_by (str | None): The sorting field provided as a query parameter.

    Raises:
        HTTPException: If `sort_by` is not `None` and is not one of the allowed values,
            an HTTP 422 Unprocessable Entity exception is raised with the detail
            "Invalid sort by field".
    """
    if sort_by is not None and sort_by not in ACTIVITY_SORT_FIELDS:
        logger.debug(
            "Rejected activity list request with an unsupported sort field",
            extra=core_logger.context(sort_by=sort_by),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    if sort_order is not None and sort_order not in ACTIVITY_SORT_ORDERS:
        logger.debug(
            "Rejected activity list request with an unsupported sort order",
            extra=core_logger.context(sort_order=sort_order),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid sort order",
        )
