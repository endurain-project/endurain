"""Typed request parameters for the activity routers.

Each alias declares its constraint on the parameter's type, so FastAPI validates it, answers a bad
value with the standard validation problem document, and publishes the accepted values in OpenAPI.
"""

from typing import Annotated

from fastapi import Query
from pydantic import AfterValidator

import core.dependencies as core_dependencies
import modules.activities.activity.constants as activity_constants

#: An activity id taken from the path.
ActivityId = core_dependencies.PositiveId


def _known_activity_type(activity_type: int | None) -> int | None:
    """Reject an activity type that is not in the vocabulary.

    Args:
        activity_type: The requested type; ``None`` means no filter.

    Returns:
        The type, unchanged.

    Raises:
        ValueError: When the type is not a known activity type.
    """
    if activity_type is not None and activity_type not in activity_constants.ACTIVITY_ID_TO_NAME:
        raise ValueError("Unknown activity type")
    return activity_type


#: The optional ``type`` filter of an activity list.
ActivityTypeFilter = Annotated[int | None, Query(alias="type"), AfterValidator(_known_activity_type)]

#: The optional ``sort_by`` key of an activity list.
SortBy = Annotated[activity_constants.ActivitySortField | None, Query()]

#: The optional ``sort_order`` direction of an activity list.
SortOrder = Annotated[activity_constants.ActivitySortOrder | None, Query()]
