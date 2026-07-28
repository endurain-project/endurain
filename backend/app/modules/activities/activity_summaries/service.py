"""Application-layer orchestration for activity summaries.

Sits between the thin route and :mod:`crud`, matching the layering the rest of
the activities module uses: the route validates and delegates, this module
resolves the anchor day, picks the bucket strategy, and returns a schema. It
raises the transport-agnostic domain errors in :mod:`core.exceptions` rather
than deciding HTTP statuses.

The route previously called CRUD directly and did its own date parsing, which
made the summaries package the one sub-module that did not follow the template.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity_summaries.crud as summary_crud
import modules.activities.activity_summaries.schema as summary_schema
import modules.users.users.integration_service as users_integration_service

logger = core_logger.get_logger(__name__)

# Widest real-world UTC offset (Pacific/Kiritimati, +14:00). The server cannot
# know the caller's timezone, so any "is this year plausible?" check has to be
# tolerant by at least this much or it rejects the caller's genuinely current
# year around New Year.
_MAX_UTC_OFFSET = timedelta(hours=14)

# Earliest year a summary may be requested for.
_MIN_YEAR = 1900

SummaryResponse = (
    summary_schema.WeeklySummaryResponse
    | summary_schema.MonthlySummaryResponse
    | summary_schema.YearlySummaryResponse
    | summary_schema.LifetimeSummaryResponse
)


def _latest_plausible_year() -> int:
    """Return the highest year any caller could currently be in.

    ``datetime.now(UTC).year`` is the *server's* year. For a user in UTC+13 that
    is still the previous year for the first 13 hours of 1 January, so validating
    against it rejected the year they are actually living in. Widening by the
    maximum real UTC offset keeps the guard (it still rejects far-future years)
    without depending on a timezone the request never carries.

    Returns:
        The latest year a caller could plausibly be in.
    """
    return (datetime.now(UTC) + _MAX_UTC_OFFSET).year


def _resolve_year(target_year: int | None, today: date) -> int:
    """Resolve and bounds-check the year a yearly summary covers.

    Args:
        target_year: The caller-supplied year, or ``None`` to use the anchor's.
        today: The resolved anchor day, used when ``target_year`` is omitted.

    Returns:
        The year to summarise.

    Raises:
        InvalidInputError: When the year is outside the plausible range.
    """
    max_year = _latest_plausible_year()
    year = target_year if target_year else today.year
    if not (_MIN_YEAR <= year <= max_year):
        logger.debug(
            "Rejected a yearly summary request with an implausible year",
            extra=core_logger.context(target_year=year, max_year=max_year),
        )
        raise core_exceptions.InvalidInputError(f"Invalid year. Must be between {_MIN_YEAR} and {max_year}.")
    return year


def build_summary(
    user_id: int,
    period: str,
    db: Session,
    *,
    anchor: date | None = None,
    target_year: int | None = None,
    activity_type: str | None = None,
) -> SummaryResponse:
    """Build the activity summary for one period.

    Args:
        user_id: The authenticated user whose activities to summarise.
        period: ``week``, ``month``, ``year`` or ``lifetime``.
        db: Database session.
        anchor: The caller's local calendar date, deciding which week/month is
            "current". Falls back to today in the user's configured timezone.
        target_year: The year a ``year`` summary covers. Defaults to the anchor's
            year.
        activity_type: Optional activity-type name filter.

    Returns:
        The summary response matching ``period``.

    Raises:
        InvalidInputError: When a ``year`` request names an implausible year.
    """
    # Server-side fallback anchor for callers that omit ``date``/``year``. The
    # web client always sends its own local date (the request carries no
    # timezone, so the server cannot derive it); when it does not, the caller's
    # configured timezone is the same frame of reference it would have sent.
    today = anchor or users_integration_service.local_today(user_id, db)

    # Which day the server thinks "today" is drives every bucket boundary, so log
    # it alongside what the caller asked for — off-by-one summary reports are
    # almost always an anchor/timezone mismatch.
    logger.debug(
        "Building an activity summary",
        extra=core_logger.context(
            user_id=user_id,
            period=period,
            anchor=anchor.isoformat() if anchor else None,
            target_year=target_year,
            activity_type=activity_type,
            resolved_today=today.isoformat(),
        ),
    )

    if period == "week":
        return summary_crud.get_weekly_summary(
            db=db,
            user_id=user_id,
            target_date=today,
            activity_type=activity_type,
        )

    if period == "month":
        return summary_crud.get_monthly_summary(
            db=db,
            user_id=user_id,
            target_date=today.replace(day=1),
            activity_type=activity_type,
        )

    if period == "year":
        return summary_crud.get_yearly_summary(
            db=db,
            user_id=user_id,
            year=_resolve_year(target_year, today),
            activity_type=activity_type,
        )

    return summary_crud.get_lifetime_summary(
        db=db,
        user_id=user_id,
        activity_type=activity_type,
    )
