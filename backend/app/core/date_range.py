"""The inclusive ``start_date`` / ``end_date`` window a list, chart or sync route accepts."""

from dataclasses import dataclass
from datetime import date
from typing import Annotated

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import Field

#: A calendar date a window is built around. The week, month and range arithmetic adds up to 32 days and a UTC
#: offset to it, so the bounds keep that inside ``date``'s year 1-9999 range; they also bracket every real record.
WindowDate = Annotated[date, Field(ge=date(1900, 1, 1), le=date(9998, 12, 31))]


@dataclass(frozen=True)
class DateRange:
    """The inclusive calendar dates a client asked a route to cover.

    Attributes:
        start_date: First day to include, or ``None`` for no lower bound.
        end_date: Last day to include, or ``None`` for no upper bound.
    """

    start_date: date | None = None
    end_date: date | None = None

    @property
    def is_set(self) -> bool:
        """Whether the client gave either date."""
        return self.start_date is not None or self.end_date is not None


def refuse_reversed_range(start_date: date | None, end_date: date | None) -> None:
    """Refuse a window whose first day is after its last day.

    Args:
        start_date: First day of the window, if given.
        end_date: Last day of the window, if given.

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


def get_date_range(
    start_date: Annotated[
        WindowDate | None, Query(description="First day to include (inclusive, `YYYY-MM-DD`).")
    ] = None,
    end_date: Annotated[
        WindowDate | None,
        Query(description="Last day to include (inclusive, `YYYY-MM-DD`). Defaults to no upper bound."),
    ] = None,
) -> DateRange:
    """Resolve the inclusive dates a list or chart is asked to cover.

    Args:
        start_date: First day to include, if the client gave one.
        end_date: Last day to include, if the client gave one.

    Returns:
        The requested dates.
    """
    refuse_reversed_range(start_date, end_date)
    return DateRange(start_date, end_date)


#: The optional window of a list or chart, declared as ``date_range: core_date_range.DateRangeQuery``.
DateRangeQuery = Annotated[DateRange, Depends(get_date_range)]
