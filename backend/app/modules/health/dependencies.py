"""Request-parameter types shared by the health routers."""

from datetime import date
from typing import Annotated

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError

import modules.health.computation as health_computation


def get_date_range(
    start_date: Annotated[
        date | None,
        Query(
            description=(
                "First day to include (inclusive, `YYYY-MM-DD`). When `start_date` or `end_date` is given, "
                "`interval` is ignored."
            )
        ),
    ] = None,
    end_date: Annotated[
        date | None,
        Query(description="Last day to include (inclusive, `YYYY-MM-DD`). Defaults to no upper bound."),
    ] = None,
) -> health_computation.DateRange:
    """Resolve the inclusive dates a health list or chart is asked to cover.

    Args:
        start_date: First day to include, if the client gave one.
        end_date: Last day to include, if the client gave one.

    Returns:
        The requested dates.

    Raises:
        RequestValidationError: When ``start_date`` is later than ``end_date`` (422).
    """
    if start_date is not None and end_date is not None and start_date > end_date:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "end_date"),
                    "msg": "end_date must not be before start_date",
                    "input": end_date.isoformat(),
                }
            ]
        )
    return health_computation.DateRange(start_date, end_date)


#: The dates of a health list or chart, declared as ``date_range: health_dependencies.DateRangeQuery``.
DateRangeQuery = Annotated[health_computation.DateRange, Depends(get_date_range)]
