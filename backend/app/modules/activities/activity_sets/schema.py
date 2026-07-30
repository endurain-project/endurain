"""Activity sets schemas."""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictFloat,
    StrictInt,
    StrictStr,
)

import core.pagination as core_pagination


class ActivitySetsBase(BaseModel):
    """
    Base schema for activity workout sets.

    Attributes:
        duration: Set duration.
        repetitions: Repetitions count.
        weight: Exercise weight.
        set_type: Workout set type string.
        start_time: Set start time ISO string.
        category: Category identifier.
        category_subtype: Category sub type.
    """

    duration: StrictFloat
    repetitions: StrictInt | None = None
    weight: StrictFloat | None = None
    set_type: StrictStr
    start_time: StrictStr
    category: StrictInt | None = None
    category_subtype: StrictInt | None = None

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


class ActivitySetsCreate(ActivitySetsBase):
    """
    Schema for creating activity workout sets.

    Attributes:
        activity_id: Parent activity ID.
    """

    activity_id: StrictInt


class ActivitySetsRead(ActivitySetsBase):
    """
    Schema for reading activity workout sets.

    ``start_time`` crosses the API as a timezone-aware UTC instant, matching the
    parent activity. Clients localize it for display using that activity's
    ``timezone`` — the server no longer ships a pre-formatted wall clock, which
    carried no offset and so could not be converted or round-tripped.

    Attributes:
        id: Activity set primary key.
        activity_id: Parent activity ID.
        start_time: Set start as a timezone-aware UTC instant.
    """

    id: StrictInt
    activity_id: StrictInt
    start_time: datetime  # type: ignore[assignment]

    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
        validate_assignment=True,
    )


#: One page of an activity's workout sets. A strength session's set count has no
#: domain ceiling, so the read is paginated rather than returning the whole set.
ActivitySetsPage = core_pagination.Page[ActivitySetsRead]
